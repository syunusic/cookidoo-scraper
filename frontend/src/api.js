const API_BASE = '/api'

export async function searchRecipes(ingredients, options = {}) {
  const params = new URLSearchParams({
    q: ingredients.join(','),
    limit: options.limit ?? 20,
    ...(options.maxMissing !== undefined && { max_missing: options.maxMissing }),
    ...(options.maxTotal !== undefined && { max_total: options.maxTotal }),
    ...(options.language && { language: options.language }),
    ...(options.country && { country: options.country }),
  })

  const res = await fetch(`${API_BASE}/recipes/search?${params}`)
  if (!res.ok) throw new Error('Error en la búsqueda')
  return res.json()
}

export async function getRecipe(id) {
  const res = await fetch(`${API_BASE}/recipes/${id}`)
  if (!res.ok) throw new Error('Receta no encontrada')
  return res.json()
}

export async function listRecipes(options = {}) {
  const params = new URLSearchParams({
    skip: options.skip ?? 0,
    limit: options.limit ?? 50,
    ...(options.language && { language: options.language }),
    ...(options.country && { country: options.country }),
  })

  const res = await fetch(`${API_BASE}/recipes/?${params}`)
  if (!res.ok) throw new Error('Error al listar recetas')
  return res.json()
}

let suggestCache = {}
export async function suggestIngredients(query) {
  if (!query || query.length < 1) return []
  if (suggestCache[query]) return suggestCache[query]

  const res = await fetch(`${API_BASE}/recipes/ingredients/suggest?q=${encodeURIComponent(query)}&limit=8`)
  if (!res.ok) return []
  const data = await res.json()
  suggestCache[query] = data.suggestions
  return data.suggestions
}
