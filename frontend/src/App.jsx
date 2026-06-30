import { useState, useEffect } from 'react'
import IngredientSearch from './components/IngredientSearch'
import RecipeList from './components/RecipeList'
import RecipeDetail from './components/RecipeDetail'
import { searchRecipes, getRecipe } from './api'

export default function App() {
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedRecipe, setSelectedRecipe] = useState(null)
  const [error, setError] = useState(null)
  const [version, setVersion] = useState('')

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setVersion(d.version || ''))
      .catch(() => {})
  }, [])

  const handleSearch = async (ingredients, options) => {
    setLoading(true)
    setError(null)
    setSelectedRecipe(null)
    try {
      const data = await searchRecipes(ingredients, options)
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleRecipeClick = async (id) => {
    setLoading(true)
    try {
      const recipe = await getRecipe(id)
      setSelectedRecipe(recipe)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-red-50">
      <header className="bg-white shadow-sm border-b border-orange-100">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
          <span className="text-3xl">🥘</span>
          <h1 className="text-xl font-bold text-gray-800">Cookidoo Recetas</h1>
          <span className="text-sm text-gray-400 ml-2">Encuentra qué cocinar con lo que tienes</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6">
        {!selectedRecipe && (
          <IngredientSearch onSearch={handleSearch} loading={loading} />
        )}

        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {loading && !selectedRecipe && (
          <div className="mt-8 flex justify-center">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-orange-300 border-t-orange-600" />
          </div>
        )}

        {results && !loading && !selectedRecipe && (
          <RecipeList
            results={results.results}
            onRecipeClick={handleRecipeClick}
            onBack={() => setResults(null)}
          />
        )}

        {selectedRecipe && (
          <RecipeDetail
            recipe={selectedRecipe}
            onBack={() => setSelectedRecipe(null)}
          />
        )}
      </main>

      <footer className="text-center text-xs text-gray-400 py-4">
        {version && <span>v{version} · </span>}
        Cookidoo Recetas
      </footer>
    </div>
  )
}
