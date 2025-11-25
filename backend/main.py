"""FastAPI backend для автоматизации подсчета времени разработки"""

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pytz import timezone
import requests
import json
import xlsxwriter
from collections import defaultdict
import tempfile
import os

app = FastAPI(title="Work Scripts Interface API")

# CORS настройки для работы с React фронтендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Настройки ===
TEAMSTORM_BASE_URL = "https://storm.alabuga.space"
MOSCOW_TZ = timezone("Europe/Moscow")
WORK_START_HOUR = 8
WORK_END_HOUR = 17

# === Pydantic модели ===
class Period(BaseModel):
    start: str  # "YYYY-MM-DD"
    end: str    # "YYYY-MM-DD"

class ProcessRequest(BaseModel):
    items: List[Dict[str, Any]]
    periods: List[Period]
    session_cookie: Optional[str] = None
    status_name: Optional[str] = "in progress"  # Статус для подсчета времени

# === Вспомогательные функции (из оригинального скрипта) ===
def parse_iso_to_msk(dt_str: str) -> datetime:
    """Парсит ISO-дату из истории (с 'Z') и переводит в МСК (timezone-aware)."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(MOSCOW_TZ)

def clamp_to_workday_window(dt: datetime) -> datetime:
    """Смещает время в границы рабочего окна [08:00, 17:00] того же дня (если нужно)."""
    day_start = dt.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    day_end = dt.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    if dt < day_start:
        return day_start
    if dt > day_end:
        return day_end
    return dt

def is_working_day(d: datetime) -> bool:
    """Пн–Пт → True; Сб(5), Вс(6) → False"""
    return d.weekday() not in (5, 6)

def add_working_time_segment(start_dt: datetime, end_dt: datetime) -> timedelta:
    """
    Возвращает длительность пересечения [start_dt, end_dt] с рабочими окнами
    (Пн–Пт, 08:00–17:00 МСК).
    """
    if end_dt <= start_dt:
        return timedelta(0)
    
    total = timedelta(0)
    cur = start_dt
    
    # Итерация по дням
    while cur.date() <= end_dt.date():
        if not is_working_day(cur):
            # Перепрыгиваем на следующий рабочий день к 08:00
            cur = (cur + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
            continue
        
        day_start = cur.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
        day_end = cur.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
        
        # Отрезок дня, который нам нужен
        seg_start = max(cur, day_start)
        seg_end = min(end_dt, day_end)
        
        if seg_start < seg_end:
            total += (seg_end - seg_start)
        
        # Переходим на следующий день, к 08:00
        cur = (cur + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    
    return total

def calculate_in_progress_time_for_period(
    history: List[Dict[str, Any]],
    period_start_str: str,
    period_end_str: str,
    status_name: str = "in progress"
) -> float:
    """
    Вычисляет время (в минутах) в указанном статусе ТОЛЬКО внутри заданного периода,
    учитывая рабочие часы и исключая выходные.
    
    Args:
        history: История изменений статусов
        period_start_str: Начало периода (YYYY-MM-DD)
        period_end_str: Конец периода (YYYY-MM-DD)
        status_name: Название статуса для подсчета (по умолчанию "in progress")
    """
    # Нормализуем статус для сравнения (lowercase)
    target_status = status_name.lower()
    
    # Период в МСК
    period_start = datetime.strptime(period_start_str, "%Y-%m-%d").replace(
        tzinfo=MOSCOW_TZ, hour=0, minute=0, second=0, microsecond=0
    )
    period_end = datetime.strptime(period_end_str, "%Y-%m-%d").replace(
        tzinfo=MOSCOW_TZ, hour=23, minute=59, second=59, microsecond=0
    )
    
    # История по времени (вся), статус меняется в entry['data']['newValue']['statusName']
    events = []
    for e in history:
        try:
            new_status = (e.get("data", {}).get("newValue", {}).get("statusName") or "").lower()
            if not e.get("date") or not new_status:
                continue
            events.append((parse_iso_to_msk(e["date"]), new_status))
        except Exception as ex:
            print(f"Ошибка при парсинге события истории: {ex}")
            continue
    
    if not events:
        print(f"Нет событий в истории для периода {period_start_str} - {period_end_str}")
        return 0.0
    
    events.sort(key=lambda x: x[0])
    
    # Логируем найденные статусы для отладки
    unique_statuses = set(status for _, status in events)
    print(f"Найденные статусы в истории: {unique_statuses}")
    print(f"Ищем статус: '{target_status}'")
    
    # Определяем состояние на момент period_start
    in_target_status = False
    for dt, status in events:
        if dt <= period_start:
            in_target_status = (status == target_status)
        else:
            break
    
    # Бежим по событиям в пределах до period_end
    last_ts = period_start
    total_td = timedelta(0)
    
    for dt, status in events:
        if dt <= period_start:
            continue
        
        if dt > period_end:
            if in_target_status:
                total_td += add_working_time_segment(last_ts, period_end)
            break
        
        # От last_ts до dt — состояние инвариантное
        if in_target_status:
            total_td += add_working_time_segment(last_ts, dt)
        
        # Обновляем состояние и маркер времени
        in_target_status = (status == target_status)
        last_ts = dt
    else:
        # Если цикл завершился без break и период не закрыт событиями
        if last_ts < period_end and in_target_status:
            total_td += add_working_time_segment(last_ts, period_end)
    
    minutes = total_td.total_seconds() / 60
    print(f"Подсчитано минут в статусе '{target_status}': {minutes:.2f}")
    return minutes

def save_to_excel_multi(
    grouped_by_period: Dict[Tuple[str, str], Dict[str, List[List[Any]]]], 
    filepath: str
) -> None:
    """Сохраняет данные в Excel файл с несколькими листами (по периоду на лист)"""
    workbook = xlsxwriter.Workbook(filepath)
    
    for (start_str, end_str), grouped_data in grouped_by_period.items():
        sheet_name = f"{start_str}_{end_str}"
        if len(sheet_name) > 31:
            sheet_name = sheet_name[:31]
        
        worksheet = workbook.add_worksheet(sheet_name)
        
        headers = ["Display Name", "Task Key", "Task Name", "In Progress Hours", "Days", "Tasks Count"]
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)
        
        row = 1
        for display_name, tasks in grouped_data.items():
            tasks = [t for t in tasks if t[2] > 0]
            if not tasks:
                continue
            
            tasks = sorted(tasks, key=lambda x: x[0])
            
            # Корректируем отображение часов для задачи: <1 часа → 1
            display_hours_list = [task[2] if task[2] >= 1 else 1 for task in tasks]
            total_hours = sum(display_hours_list)
            total_days = round(total_hours / 8, 1)
            tasks_count = len(tasks)
            
            if len(tasks) > 1:
                worksheet.merge_range(row, 0, row + len(tasks) - 1, 0, display_name)
                worksheet.merge_range(row, 4, row + len(tasks) - 1, 4, total_days)
                worksheet.merge_range(row, 5, row + len(tasks) - 1, 5, tasks_count)
            else:
                worksheet.write(row, 0, display_name)
                worksheet.write(row, 4, total_days)
                worksheet.write(row, 5, tasks_count)
            
            for i, task in enumerate(tasks):
                task_key, task_name, hours = task
                display_hours = display_hours_list[i]
                worksheet.write(row, 1, task_key)
                worksheet.write(row, 2, task_name)
                worksheet.write(row, 3, display_hours)
                row += 1
    
    workbook.close()

# === API Endpoints ===
@app.get("/")
async def root():
    return {"message": "Work Scripts Interface API", "status": "running"}

@app.get("/api/workspaces")
async def get_workspaces(session_cookie: str):
    """
    Получает список всех workspace (проектов) из TeamStorm.
    """
    base_url = TEAMSTORM_BASE_URL
    cookies = {"session": session_cookie}
    
    try:
        # Пробуем разные возможные эндпоинты для получения workspace
        possible_endpoints = [
            "/api/v1/workspaces",
            "/api/workspaces",
            "/api/v1/user/workspaces",
            "/rest/api/1.0/workspaces",
            "/rest/api/workspaces",
        ]
        
        for endpoint in possible_endpoints:
            try:
                url = f"{base_url}{endpoint}"
                print(f"Попытка получить workspace из: {url}")
                resp = requests.get(url, cookies=cookies, timeout=10)
                print(f"Статус ответа: {resp.status_code}")
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Получены данные: {type(data)}, ключи: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                    
                    # Обрабатываем разные форматы ответа
                    if isinstance(data, list):
                        workspaces = data
                    elif isinstance(data, dict) and "workspaces" in data:
                        workspaces = data["workspaces"]
                    elif isinstance(data, dict) and "items" in data:
                        workspaces = data["items"]
                    elif isinstance(data, dict) and "data" in data:
                        workspaces = data["data"]
                    else:
                        workspaces = [data] if data else []
                    
                    # Форматируем ответ
                    result = []
                    for ws in workspaces:
                        if isinstance(ws, dict):
                            result.append({
                                "id": ws.get("id") or ws.get("workspaceId") or ws.get("_id"),
                                "name": ws.get("name") or ws.get("title") or ws.get("displayName") or ws.get("workspaceName", "Без названия"),
                                "key": ws.get("key") or ws.get("workspaceKey"),
                            })
                    
                    if result:
                        print(f"Найдено workspace: {len(result)}")
                        return {"workspaces": result}
                else:
                    print(f"Ошибка {resp.status_code}: {resp.text[:200]}")
            except requests.RequestException as e:
                print(f"Ошибка запроса к {endpoint}: {e}")
                continue
            except Exception as e:
                print(f"Неожиданная ошибка при обработке {endpoint}: {e}")
                continue
        
        raise HTTPException(status_code=404, detail="Не удалось найти эндпоинт для получения workspace")
    except Exception as e:
        print(f"Ошибка при получении workspace: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка проектов: {str(e)}")

@app.get("/api/workspaces/{workspace_id}/workitems")
async def get_workitems(workspace_id: str, session_cookie: str):
    """
    Получает список всех задач (workitems) из указанного workspace.
    """
    base_url = TEAMSTORM_BASE_URL
    cookies = {"session": session_cookie}
    
    try:
        # Пробуем разные возможные эндпоинты
        possible_endpoints = [
            f"/api/v1/workspaces/{workspace_id}/workItems",
            f"/api/workspaces/{workspace_id}/workItems",
            f"/api/v1/workspaces/{workspace_id}/items",
            f"/api/workspaces/{workspace_id}/items",
            f"/rest/api/1.0/workspaces/{workspace_id}/workItems",
            f"/rest/api/workspaces/{workspace_id}/workItems",
        ]
        
        all_items = []
        
        for endpoint in possible_endpoints:
            try:
                url = f"{base_url}{endpoint}"
                print(f"Попытка получить workitems из: {url}")
                resp = requests.get(url, cookies=cookies, timeout=30)
                print(f"Статус ответа: {resp.status_code}")
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Получены данные: {type(data)}, ключи: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                    
                    # Обрабатываем разные форматы ответа
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict) and "items" in data:
                        items = data["items"]
                    elif isinstance(data, dict) and "workItems" in data:
                        items = data["workItems"]
                    elif isinstance(data, dict) and "data" in data:
                        items = data["data"]
                    elif isinstance(data, dict) and "results" in data:
                        items = data["results"]
                    else:
                        items = [data] if data else []
                    
                    print(f"Найдено элементов: {len(items)}")
                    
                    # Форматируем задачи
                    for item in items:
                        if isinstance(item, dict):
                            formatted_item = {
                                "key": item.get("key") or item.get("id") or item.get("_id"),
                                "name": item.get("name") or item.get("title") or item.get("displayName") or item.get("workItemName", "Без названия"),
                                "workspaceId": workspace_id,
                                "workitemId": item.get("id") or item.get("workitemId") or item.get("workItemId") or item.get("_id"),
                                "assignee": item.get("assignee") or {},
                            }
                            # Проверяем, что есть все необходимые поля
                            if formatted_item["key"] and formatted_item["workitemId"]:
                                all_items.append(formatted_item)
                    
                    if all_items:
                        print(f"Отформатировано задач: {len(all_items)}")
                        return {"items": all_items, "count": len(all_items)}
                else:
                    print(f"Ошибка {resp.status_code}: {resp.text[:200]}")
            except requests.RequestException as e:
                print(f"Ошибка при запросе {endpoint}: {e}")
                continue
            except Exception as e:
                print(f"Неожиданная ошибка при обработке {endpoint}: {e}")
                continue
        
        if not all_items:
            raise HTTPException(status_code=404, detail=f"Не удалось получить задачи для workspace {workspace_id}")
        
        return {"items": all_items, "count": len(all_items)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка при получении workitems: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении задач: {str(e)}")

@app.post("/api/process")
async def process_data(request: ProcessRequest):
    """
    Обрабатывает данные и генерирует Excel файл.
    Возвращает путь к файлу для скачивания.
    """
    if not request.periods:
        raise HTTPException(status_code=400, detail="Список periods пуст.")
    
    base_url = f"{TEAMSTORM_BASE_URL}/history/api/v1"
    grouped_by_period: Dict[Tuple[str, str], Dict[str, List[List[Any]]]] = {
        (p.start, p.end): defaultdict(list) for p in request.periods
    }
    
    cookies = {}
    if request.session_cookie:
        cookies = {"session": request.session_cookie}
    
    for item in request.items:
        key = item.get("key")
        workspace_id = item.get("workspaceId")
        workitem_id = item.get("workitemId")
        
        if not key or not workspace_id or not workitem_id:
            print(f"Пропущен элемент из-за отсутствия ключевых данных: {item}")
            continue
        
        # Тянем историю один раз
        history_url = f"{base_url}/workspaces/{workspace_id}/workItems/{workitem_id}/history"
        try:
            resp = requests.get(history_url, cookies=cookies)
            resp.raise_for_status()
            history_data = resp.json()
            
            # Только события смены статуса
            filtered_history = [
                {
                    "date": entry.get("date"),
                    "type": entry.get("type"),
                    "data": entry.get("data"),
                }
                for entry in history_data
                if entry.get("type") == "StatusUpdated"
            ]
            
            # Данные задачи
            assignee = item.get("assignee", {}) or {}
            display_name = assignee.get("displayName", "Не указано")
            task_name = item.get("name", "Не указано")
            
            # Для каждого периода считаем часы отдельно
            status_to_search = request.status_name or "in progress"
            print(f"Обработка задачи {key}, статус для поиска: '{status_to_search}'")
            print(f"Количество событий в истории: {len(filtered_history)}")
            
            for period in request.periods:
                mins = calculate_in_progress_time_for_period(
                    filtered_history, period.start, period.end, status_to_search
                )
                hours = round(mins / 60, 1)
                
                print(f"Задача {key}, период {period.start}-{period.end}: {hours} часов")
                
                if hours > 0:
                    grouped_by_period[(period.start, period.end)][display_name].append(
                        [key, task_name, hours]
                    )
            
            print(f"История обработана для key={key}")
        except requests.RequestException as e:
            print(f"Ошибка при запросе {history_url}: {e}")
            continue
    
    # Создаем временный файл для Excel
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    temp_filepath = temp_file.name
    temp_file.close()
    
    # Сохранение в Excel
    save_to_excel_multi(grouped_by_period, temp_filepath)
    
    return {"filepath": temp_filepath, "filename": "report.xlsx"}

@app.get("/api/download/{filepath:path}")
async def download_file(filepath: str, background_tasks: BackgroundTasks):
    """Скачивание сгенерированного Excel файла"""
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # Удаляем файл после отправки
    def cleanup():
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
    
    background_tasks.add_task(cleanup)
    
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="report.xlsx"
    )

@app.post("/api/upload-json")
async def upload_json_file(file: UploadFile = File(...)):
    """Загрузка JSON файла с данными items"""
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
        items = data.get("items", [])
        return {"items": items, "count": len(items)}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Неверный формат JSON файла")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке файла: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

