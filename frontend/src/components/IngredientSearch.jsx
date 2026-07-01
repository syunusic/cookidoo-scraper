import { useState, useEffect, useRef } from 'react'
import { suggestIngredients, recognizeIngredients } from '../api'

export default function IngredientSearch({ ingredients, setIngredients, onSearch, loading, collapsed }) {
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [selectedSuggestion, setSelectedSuggestion] = useState(-1)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [filterMissing, setFilterMissing] = useState(false)
  const [maxMissing, setMaxMissing] = useState(3)
  const [filterTotal, setFilterTotal] = useState(false)
  const [maxTotal, setMaxTotal] = useState(15)
  const [recognizing, setRecognizing] = useState(false)
  const [textMode, setTextMode] = useState(false)
  const [msg, setMsg] = useState('')
  const inputRef = useRef(null)
  const cameraRef = useRef(null)
  const suggestTimer = useRef(null)

  useEffect(() => {
    if (suggestTimer.current) clearTimeout(suggestTimer.current)

    const last = input.split(',').pop().trim()
    if (!last || last.length < 1) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }

    suggestTimer.current = setTimeout(async () => {
      const result = await suggestIngredients(last)
      setSuggestions(result)
      setShowSuggestions(result.length > 0 && last.length > 0)
      setSelectedSuggestion(-1)
    }, 200)

    return () => {
      if (suggestTimer.current) clearTimeout(suggestTimer.current)
    }
  }, [input])

  const commitIngredient = (item) => {
    const parts = input.split(',')
    parts[parts.length - 1] = item
    setInput(parts.join(', ') + ', ')
    setShowSuggestions(false)
    inputRef.current?.focus()
  }

  const addIngredient = () => {
    const items = input.split(',').map(s => s.trim()).filter(Boolean)
    if (items.length > 0) {
      setIngredients(prev => {
        const existing = new Set(prev.map(i => i.toLowerCase()))
        const newItems = items.filter(i => !existing.has(i.toLowerCase()))
        return [...prev, ...newItems]
      })
      setInput('')
    }
  }

  const removeIngredient = (index) => {
    setIngredients(prev => prev.filter((_, i) => i !== index))
  }

  const compressImage = (file, maxW = 1200, quality = 0.8) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const img = new Image()
        img.onload = () => {
          let w = img.width, h = img.height
          if (w > maxW || h > maxW) {
            const ratio = Math.min(maxW / w, maxW / h)
            w = Math.round(w * ratio)
            h = Math.round(h * ratio)
          }
          const canvas = document.createElement('canvas')
          canvas.width = w
          canvas.height = h
          const ctx = canvas.getContext('2d')
          ctx.drawImage(img, 0, 0, w, h)
          canvas.toBlob(blob => {
            if (blob) resolve(new File([blob], file.name || 'photo.jpg', { type: 'image/jpeg' }))
            else resolve(file)
          }, 'image/jpeg', quality)
        }
        img.onerror = () => resolve(file)
        img.src = reader.result
      }
      reader.onerror = () => resolve(file)
      reader.readAsDataURL(file)
    })
  }

  const handleCameraCapture = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setMsg('')
    setRecognizing(true)
    try {
      const compressed = await compressImage(file)
      const mode = textMode ? 'text' : 'visual'
      const ingredients = await recognizeIngredients(compressed, mode)
      if (ingredients.length > 0) {
        setIngredients(prev => {
          const existing = new Set(prev.map(i => i.toLowerCase()))
          const newItems = ingredients.filter(i => !existing.has(i.toLowerCase()))
          return [...prev, ...newItems]
        })
        setMsg(`Reconocidos: ${ingredients.join(', ')}`)
      } else {
        setMsg('No se reconocieron ingredientes en la foto')
      }
    } catch (err) {
      console.error(err)
      setMsg('Error al procesar la foto')
    } finally {
      setRecognizing(false)
      e.target.value = ''
      setTimeout(() => setMsg(''), 5000)
    }
  }

  if (collapsed) return null

  const handleKeyDown = (e) => {
    if (showSuggestions) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedSuggestion(prev => Math.min(prev + 1, suggestions.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedSuggestion(prev => Math.max(prev - 1, 0))
        return
      }
      if (e.key === 'Enter' && selectedSuggestion >= 0) {
        e.preventDefault()
        commitIngredient(suggestions[selectedSuggestion])
        return
      }
      if (e.key === 'Escape') {
        setShowSuggestions(false)
        return
      }
    }

    if (e.key === 'Enter' && input.trim()) {
      e.preventDefault()
      addIngredient()
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (ingredients.length === 0) return
    const options = {}
    if (filterMissing) options.maxMissing = maxMissing
    if (filterTotal) options.maxTotal = maxTotal
    onSearch(options)
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 border border-orange-100">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">
        ¿Qué ingredientes tienes?
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="relative flex gap-2 mb-3">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              placeholder="Ej: huevos, leche, harina"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-400 focus:border-orange-400 outline-none"
              disabled={loading}
            />
            {showSuggestions && (
              <ul className="absolute z-10 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                {suggestions.map((s, i) => (
                  <li
                    key={s}
                    onMouseDown={() => commitIngredient(s)}
                    className={`px-4 py-2 text-sm cursor-pointer hover:bg-orange-50 ${
                      i === selectedSuggestion ? 'bg-orange-100 font-medium' : ''
                    }`}
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            onClick={addIngredient}
            className="px-4 py-2.5 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 font-medium"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => cameraRef.current?.click()}
            disabled={recognizing}
            className={`px-3 py-2.5 rounded-lg font-medium disabled:opacity-50 ${
              textMode
                ? 'bg-orange-100 text-orange-700 border border-orange-300'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            title={textMode ? "Foto de texto (etiqueta/receta)" : "Foto de ingredientes"}
          >
            {recognizing ? (
              <span className="inline-block w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
            ) : textMode ? (
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
                <path d="M7 13l3 3 6-6" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            )}
          </button>
          <button
            type="button"
            onClick={() => setTextMode(!textMode)}
            className={`px-3 py-2.5 rounded-lg text-sm flex items-center gap-1 ${
              textMode
                ? 'bg-orange-500 text-white shadow-sm'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
            title={textMode ? "Cambiar a modo visual" : "Cambiar a modo texto (leer etiquetas)"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            <span className="hidden sm:inline">Texto</span>
          </button>
          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleCameraCapture}
            className="hidden"
          />
        </div>

        <div className="mb-3 space-y-1.5">
          <div className="flex items-center gap-2 text-xs">
            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full ${
              textMode ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                textMode ? 'bg-orange-500' : 'bg-green-500'
              }`} />
              {textMode ? '🔤 Modo texto' : '📷 Modo visual'}
            </span>
            <button
              type="button"
              onClick={() => setTextMode(!textMode)}
              className="text-gray-400 hover:text-gray-700 underline decoration-dotted"
            >
              {textMode ? 'cambiar a visual' : 'cambiar a texto'}
            </button>
          </div>
          <div className="text-xs text-gray-400 leading-relaxed">
            {textMode ? (
              <span>Lee texto en la foto (etiquetas, listas de compras, recetas escritas)</span>
            ) : (
              <span>Reconoce alimentos visualmente (frutas, verduras, carnes, etc.)</span>
            )}
          </div>
        </div>

        {msg && (
          <div className="mb-3 text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2 text-center">
            {msg}
          </div>
        )}

        {ingredients.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {ingredients.map((ing, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-orange-100 text-orange-800 rounded-full text-sm"
              >
                {ing}
                <button
                  type="button"
                  onClick={() => removeIngredient(i)}
                  className="text-orange-500 hover:text-orange-700 font-bold"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-4 mb-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={filterMissing}
              onChange={(e) => setFilterMissing(e.target.checked)}
              className="rounded border-gray-300 text-orange-500 focus:ring-orange-400"
            />
            Máx. faltantes
            <select
              value={maxMissing}
              onChange={(e) => setMaxMissing(Number(e.target.value))}
              disabled={!filterMissing}
              className="border border-gray-300 rounded px-2 py-1 text-sm disabled:opacity-50"
            >
              {[1,2,3,4,5,6,7,8,9,10].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={filterTotal}
              onChange={(e) => setFilterTotal(e.target.checked)}
              className="rounded border-gray-300 text-orange-500 focus:ring-orange-400"
            />
            Máx. ingredientes
            <select
              value={maxTotal}
              onChange={(e) => setMaxTotal(Number(e.target.value))}
              disabled={!filterTotal}
              className="border border-gray-300 rounded px-2 py-1 text-sm disabled:opacity-50"
            >
              {[5,10,15,20,25,30].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
        </div>

        <button
          type="submit"
          disabled={ingredients.length === 0 || loading}
          className="w-full py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 text-white font-semibold rounded-xl transition-colors"
        >
          {loading ? 'Buscando...' : 'Buscar recetas'}
        </button>
      </form>
    </div>
  )
}
