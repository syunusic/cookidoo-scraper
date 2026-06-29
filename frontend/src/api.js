const API_BASE = '/api'

export async function searchRecipes(ingredients, options = {}) {
  const params = new URLSearchParams({
    q: ingredients.join(','),
    max_missing: options.maxMissing ?? 3,
    limit: options.limit ?? 20,
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
