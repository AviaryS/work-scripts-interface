import React, { useState } from 'react'
import axios from 'axios'
import './App.css'

interface Period {
  start: string
  end: string
}

interface Item {
  key: string
  name: string
  workspaceId: string
  workitemId: string
  assignee?: {
    displayName: string
  }
}

interface Workspace {
  id: string
  name: string
  key?: string
}

function App() {
  const [jsonFile, setJsonFile] = useState<File | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [periods, setPeriods] = useState<Period[]>([
    { start: '', end: '' }
  ])
  const [sessionCookie, setSessionCookie] = useState('')
  const [statusName, setStatusName] = useState('in progress')
  const [customStatus, setCustomStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  
  // Новые состояния для работы с TeamStorm
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('')
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false)
  const [loadingItems, setLoadingItems] = useState(false)

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setJsonFile(file)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await axios.post('http://localhost:8000/api/upload-json', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      setItems(response.data.items)
      setSuccess(`Загружено ${response.data.count} задач`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при загрузке файла')
    }
  }

  const loadWorkspaces = async () => {
    if (!sessionCookie) {
      setError('Сначала введите session cookie')
      return
    }

    setLoadingWorkspaces(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await axios.get('http://localhost:8000/api/workspaces', {
        params: { session_cookie: sessionCookie }
      })
      setWorkspaces(response.data.workspaces || [])
      setSuccess(`Загружено ${response.data.workspaces?.length || 0} проектов`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при загрузке списка проектов')
    } finally {
      setLoadingWorkspaces(false)
    }
  }

  const loadWorkItems = async () => {
    if (!selectedWorkspaceId) {
      setError('Выберите проект')
      return
    }

    if (!sessionCookie) {
      setError('Session cookie обязателен')
      return
    }

    setLoadingItems(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await axios.get(
        `http://localhost:8000/api/workspaces/${selectedWorkspaceId}/workitems`,
        {
          params: { session_cookie: sessionCookie }
        }
      )
      setItems(response.data.items || [])
      setSuccess(`Загружено ${response.data.count || 0} задач из проекта`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при загрузке задач')
    } finally {
      setLoadingItems(false)
    }
  }

  const addPeriod = () => {
    setPeriods([...periods, { start: '', end: '' }])
  }

  const removePeriod = (index: number) => {
    setPeriods(periods.filter((_, i) => i !== index))
  }

  const updatePeriod = (index: number, field: 'start' | 'end', value: string) => {
    const updated = [...periods]
    updated[index][field] = value
    setPeriods(updated)
  }

  const handleProcess = async () => {
    if (items.length === 0) {
      setError('Сначала загрузите данные (из проекта или JSON файла)')
      return
    }

    const validPeriods = periods.filter(p => p.start && p.end)
    if (validPeriods.length === 0) {
      setError('Добавьте хотя бы один период')
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const finalStatusName = statusName === 'custom' ? customStatus : statusName
      
      const response = await axios.post('http://localhost:8000/api/process', {
        items,
        periods: validPeriods,
        session_cookie: sessionCookie || undefined,
        status_name: finalStatusName,
      })

      // Скачиваем файл
      const fileResponse = await axios.get(
        `http://localhost:8000/api/download/${encodeURIComponent(response.data.filepath)}`,
        { responseType: 'blob' }
      )

      // Создаем ссылку для скачивания
      const url = window.URL.createObjectURL(new Blob([fileResponse.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', response.data.filename || 'report.xlsx')
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      setSuccess('Excel файл успешно сгенерирован и скачан!')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка при обработке данных')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="container">
        <h1>Work Scripts Interface</h1>
        <p className="subtitle">Автоматизация подсчета времени разработки</p>

        {/* Session Cookie */}
        <div className="section">
          <h2>1. Session Cookie для доступа к TeamStorm</h2>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <input
                type="text"
                value={sessionCookie}
                onChange={(e) => setSessionCookie(e.target.value)}
                placeholder="Вставьте session cookie из браузера"
                className="text-input"
              />
            </div>
            <button
              onClick={loadWorkspaces}
              disabled={loadingWorkspaces || !sessionCookie}
              className="btn-secondary"
              type="button"
            >
              {loadingWorkspaces ? 'Загрузка...' : 'Загрузить проекты'}
            </button>
          </div>
          <p style={{ fontSize: '0.9em', color: '#666', marginTop: '8px' }}>
            Как получить cookie: откройте TeamStorm в браузере → F12 → Application → Cookies → скопируйте значение session
          </p>
        </div>

        {/* Выбор проекта из TeamStorm */}
        {workspaces.length > 0 && (
          <div className="section">
            <h2>2. Выберите проект из TeamStorm</h2>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <select
                  value={selectedWorkspaceId}
                  onChange={(e) => setSelectedWorkspaceId(e.target.value)}
                  className="select-input"
                >
                  <option value="">-- Выберите проект --</option>
                  {workspaces.map((ws) => (
                    <option key={ws.id} value={ws.id}>
                      {ws.name} {ws.key ? `(${ws.key})` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={loadWorkItems}
                disabled={loadingItems || !selectedWorkspaceId || !sessionCookie}
                className="btn-secondary"
                type="button"
              >
                {loadingItems ? 'Загрузка...' : 'Загрузить задачи'}
              </button>
            </div>
            {items.length > 0 && (
              <div className="info" style={{ marginTop: '12px' }}>
                Загружено задач из проекта: <strong>{items.length}</strong>
              </div>
            )}
          </div>
        )}

        {/* Альтернатива: Загрузка JSON файла */}
        <div className="section">
          <h2>{workspaces.length > 0 ? '3. Или загрузите JSON файл (альтернатива)' : '2. Или загрузите JSON файл'}</h2>
          <div className="file-upload">
            <input
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="file-input"
              id="json-file-input"
            />
            <label htmlFor="json-file-input" className="file-label">
              {jsonFile ? jsonFile.name : 'Выберите JSON файл'}
            </label>
          </div>
          {items.length > 0 && !selectedWorkspaceId && (
            <div className="info">
              Загружено задач: <strong>{items.length}</strong>
            </div>
          )}
        </div>

        {/* Настройка периодов */}
        <div className="section">
          <h2>{workspaces.length > 0 ? '4. Настройте периоды' : '3. Настройте периоды'}</h2>
          {periods.map((period, index) => (
            <div key={index} className="period-row">
              <input
                type="date"
                value={period.start}
                onChange={(e) => updatePeriod(index, 'start', e.target.value)}
                placeholder="Начало периода"
                className="date-input"
              />
              <span className="date-separator">—</span>
              <input
                type="date"
                value={period.end}
                onChange={(e) => updatePeriod(index, 'end', e.target.value)}
                placeholder="Конец периода"
                className="date-input"
              />
              {periods.length > 1 && (
                <button
                  onClick={() => removePeriod(index)}
                  className="btn-remove"
                  type="button"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          <button onClick={addPeriod} className="btn-secondary" type="button">
            + Добавить период
          </button>
        </div>

        {/* Status Name */}
        <div className="section">
          <h2>{workspaces.length > 0 ? '5. Выберите статус для подсчета' : '4. Выберите статус для подсчета'}</h2>
          <select
            value={statusName}
            onChange={(e) => setStatusName(e.target.value)}
            className="select-input"
          >
            <option value="in progress">in progress (английская О)</option>
            <option value="in prоgress">in prоgress (русская О)</option>
            <option value="in progrеss">in progrеss (русская е)</option>
            <option value="custom">Другой статус (укажите ниже)</option>
          </select>
          {statusName === 'custom' && (
            <input
              type="text"
              value={customStatus}
              onChange={(e) => setCustomStatus(e.target.value)}
              placeholder="Введите название статуса"
              className="text-input"
              style={{ marginTop: '12px' }}
            />
          )}
        </div>


        {/* Кнопка обработки */}
        <div className="section">
          <button
            onClick={handleProcess}
            disabled={loading || items.length === 0}
            className="btn-primary"
          >
            {loading ? 'Обработка...' : 'Сгенерировать Excel'}
          </button>
        </div>

        {/* Сообщения об ошибках и успехе */}
        {error && <div className="message error">{error}</div>}
        {success && <div className="message success">{success}</div>}
      </div>
    </div>
  )
}

export default App

