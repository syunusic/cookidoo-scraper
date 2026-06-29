export default function RecipeDetail({ recipe, onBack }) {
  if (!recipe) return null

  return (
    <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
      <div className="relative">
        {recipe.image_url && (
          <img
            src={recipe.image_url}
            alt={recipe.name}
            className="w-full h-64 object-cover"
          />
        )}
        <button
          onClick={onBack}
          className="absolute top-4 left-4 bg-white/90 hover:bg-white px-4 py-2 rounded-lg shadow text-sm font-medium text-gray-700 transition-colors"
        >
          ← Volver
        </button>
      </div>

      <div className="p-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-2">{recipe.name}</h2>

        <div className="flex flex-wrap gap-4 text-sm text-gray-500 mb-4">
          {recipe.total_time && (
            <span className="inline-flex items-center gap-1">⏱ {recipe.total_time}</span>
          )}
          {recipe.difficulty && (
            <span className="inline-flex items-center gap-1">👨‍🍳 {recipe.difficulty}</span>
          )}
          {recipe.yield_amount && (
            <span className="inline-flex items-center gap-1">🍽 {recipe.yield_amount}</span>
          )}
          {recipe.rating && (
            <span className="inline-flex items-center gap-1">
              ★ {recipe.rating} ({recipe.review_count || 0})
            </span>
          )}
        </div>

        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-700 mb-3">Ingredientes</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {recipe.ingredients?.map((ing) => (
              <div
                key={ing.id}
                className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg"
              >
                <span className="w-2 h-2 bg-orange-400 rounded-full flex-shrink-0" />
                <span className="text-sm text-gray-700">{ing.raw_text}</span>
              </div>
            ))}
          </div>
        </div>

        {recipe.url && (
          <a
            href={recipe.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-xl transition-colors"
          >
            Ver receta original en Cookidoo
            <span>↗</span>
          </a>
        )}
      </div>
    </div>
  )
}
