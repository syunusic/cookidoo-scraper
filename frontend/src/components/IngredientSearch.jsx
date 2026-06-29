import { useState } from 'react'

export default function IngredientSearch({ onSearch, loading }) {
  const [input, setInput] = useState('')
  const [ingredients, setIngredients] = useState([])
  const [maxMissing, setMaxMissing] = useState(3)

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
    if (e.key === 'Enter' && input.trim()) {
      e.preventDefault()
      addIngredient()
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (ingredients.length === 0) return
    onSearch(ingredients, { maxMissing })
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 border border-orange-100">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">
        ¿Qué ingredientes tienes?
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ej: huevos, leche, harina"
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-400 focus:border-orange-400 outline-none"
            disabled={loading}
          />
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

        <div className="flex items-center gap-4 mb-4">
          <label className="text-sm text-gray-600">
            Máx. ingredientes faltantes:
          </label>
          <select
            value={maxMissing}
            onChange={(e) => setMaxMissing(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
          >
            {[0, 1, 2, 3, 4, 5].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
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
