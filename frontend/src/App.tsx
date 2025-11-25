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

function App() {
  const [jsonFile, setJsonFile] = useState<File | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [periods, setPeriods] = useState<Period[]>([
    { start: '', end: '' }
  ])
  const [sessionCookie, setSessionCookie] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

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
      setError('Сначала загрузите JSON файл с данными')
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
      const response = await axios.post('http://localhost:8000/api/process', {
        items,
        periods: validPeriods,
        session_cookie: sessionCookie || undefined,
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

        {/* Загрузка JSON файла */}
        <div className="section">
          <h2>1. Загрузите JSON файл с данными</h2>
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
          {items.length > 0 && (
            <div className="info">
              Загружено задач: <strong>{items.length}</strong>
            </div>
          )}
        </div>

        {/* Настройка периодов */}
        <div className="section">
          <h2>2. Настройте периоды</h2>
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

        {/* Session Cookie */}
        <div className="section">
          <h2>3. Session Cookie (опционально)</h2>
          <input
            type="text"
            value={sessionCookie}
            onChange={(e) => setSessionCookie(e.target.value)}
            placeholder="Вставьте session cookie для доступа к API"
            className="text-input"
          />
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

