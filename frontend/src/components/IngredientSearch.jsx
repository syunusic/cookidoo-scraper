import { useState, useEffect, useRef } from 'react'
import { suggestIngredients } from '../api'

export default function IngredientSearch({ onSearch, loading }) {
  const [input, setInput] = useState('')
  const [ingredients, setIngredients] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [selectedSuggestion, setSelectedSuggestion] = useState(-1)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef(null)
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
    onSearch(ingredients, {})
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
        </div>

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
