export default function RecipeList({ results, onRecipeClick, onBack }) {
  if (!results || results.length === 0) {
    return (
      <div className="mt-8 text-center py-12 bg-white rounded-2xl shadow">
        <p className="text-gray-500 text-lg">
          No se encontraron recetas con esos ingredientes.
        </p>
        <button onClick={onBack} className="mt-4 text-orange-500 hover:text-orange-700 font-medium">
          Volver
        </button>
      </div>
    )
  }

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-700">
          {results.length} receta{results.length !== 1 ? 's' : ''} encontrada{results.length !== 1 ? 's' : ''}
        </h2>
        <button onClick={onBack} className="text-sm text-orange-500 hover:text-orange-700 font-medium">
          ← Nueva búsqueda
        </button>
      </div>

      <div className="space-y-3">
        {results.map((result) => {
          const r = result.recipe
          const pct = Math.round((result.matched_ingredients / result.total_ingredients) * 100)

          return (
            <div
              key={r.id}
              onClick={() => onRecipeClick(r.id)}
              className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 hover:shadow-md hover:border-orange-200 transition-all cursor-pointer"
            >
              <div className="flex gap-4">
                {r.image_url && (
                  <img
                    src={r.image_url}
                    alt={r.name}
                    className="w-20 h-20 object-cover rounded-lg flex-shrink-0"
                    loading="lazy"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-800 truncate">{r.name}</h3>
                  <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                    {r.total_time && <span>⏱ {r.total_time}</span>}
                    {r.difficulty && <span>• {r.difficulty}</span>}
                    {r.yield_amount && <span>• {r.yield_amount}</span>}
                  </div>

                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-700">
                      {result.matched_ingredients}/{result.total_ingredients}
                    </span>
                    <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden max-w-24">
                      <div
                        className="h-full bg-green-500 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    {result.missing_ingredients.length > 0 ? (
                      <span className="text-xs text-amber-600">
                        Faltan {result.missing_ingredients.length}
                      </span>
                    ) : (
                      <span className="text-xs text-green-600 font-medium">
                        ¡Tienes todo!
                      </span>
                    )}
                  </div>

                  {result.missing_ingredients.length > 0 && (
                    <div className="mt-1 text-xs text-gray-400 truncate">
                      Falta: {result.missing_ingredients.slice(0, 3).join(', ')}
                      {result.missing_ingredients.length > 3 && '...'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
