"""
Google Cloud Vision integration for ingredient recognition.
Uses REST API directly with API key authentication (no google-cloud-vision SDK needed).
Falls back gracefully if API key is not configured.
"""
import base64
import os
import re
import logging

import requests

from app.vision import FOOD_MAP, NON_FOOD_WORDS

logger = logging.getLogger(__name__)

API_URL = "https://vision.googleapis.com/v1/images:annotate"
_api_key = None

# Additional label → ingredient mappings specific to Google Vision labels
# (Google Vision returns many labels that ImageNet doesn't have)
GV_FOOD_MAP = {
    "celery stalk": "apio",
    "leaf vegetable": "espinaca",
    "root vegetable": "zanahoria",
    "bulb vegetable": "cebolla",
    "allium": "ajo",
    "allium ampeloprasum": "puerro",
    "dairy product": "leche",
    "meat": "carne",
    "poultry": "pollo",
    "seafood": "pescado",
    "citrus fruit": "limón",
    "tropical fruit": "mango",
    "stone fruit": "melocotón",
    "berry": "fresa",
    "sweet pepper": "pimiento",
    "bell pepper": "pimiento",
    "chili pepper": "chile",
    "cruciferous vegetable": "brócoli",
    "brassica oleracea": "repollo",
    "edible fungi": "champiñón",
    "mushroom family": "champiñón",
    "sausage": "salchicha",
    "breakfast sausage": "salchicha",
    "pork sausage": "salchicha",
    "italian sausage": "salchicha",
    "bread roll": "pan",
    "baguette": "pan",
    "baked goods": "pan",
    "cheese": "queso",
    "hard cheese": "queso",
    "soft cheese": "queso",
    "cheese board": "queso",
    "chocolate bar": "chocolate",
    "chocolate candy": "chocolate",
    "dark chocolate": "chocolate",
    "milk chocolate": "chocolate",
    "pasta": "pasta",
    "pasta salad": "pasta",
    "spaghetti bolognese": "pasta",
    "lasagne": "pasta",
    "rice": "arroz",
    "risotto": "arroz",
    "white rice": "arroz",
    "brown rice": "arroz",
    "bean": "frijol",
    "legume": "lenteja",
    "pulse": "lenteja",
    "lamb and mutton": "cordero",
    "beef": "res",
    "ground beef": "carne molida",
    "minced meat": "carne molida",
    "pork": "cerdo",
    "chicken": "pollo",
    "chicken meat": "pollo",
    "chicken thigh": "muslo de pollo",
    "chicken breast": "pechuga de pollo",
    "duck": "pato",
    "fish": "pescado",
    "salmon": "salmón",
    "tuna": "atún",
    "cod": "bacalao",
    "shrimp": "camarón",
    "prawn": "camarón",
    "egg": "huevo",
    "hen egg": "huevo",
    "chicken egg": "huevo",
    "butter": "mantequilla",
    "milk": "leche",
    "yogurt": "yogur",
    "cream": "crema",
    "tomato": "tomate",
    "cherry tomato": "tomate",
    "plum tomato": "tomate",
    "potato": "patata",
    "sweet potato": "boniato",
    "carrot": "zanahoria",
    "onion": "cebolla",
    "red onion": "cebolla",
    "white onion": "cebolla",
    "garlic": "ajo",
    "garlic clove": "ajo",
    "leek": "puerro",
    "cucumber": "pepino",
    "zucchini": "calabacín",
    "eggplant": "berenjena",
    "avocado": "aguacate",
    "bell pepper": "pimiento",
    "green pepper": "pimiento",
    "red pepper": "pimiento",
    "yellow pepper": "pimiento",
    "orange pepper": "pimiento",
    "broccoli": "brócoli",
    "cauliflower": "coliflor",
    "cabbage": "repollo",
    "spinach": "espinaca",
    "lettuce": "lechuga",
    "arugula": "rúcula",
    "kale": "col rizada",
    "celery": "apio",
    "asparagus": "espárrago",
    "artichoke": "alcachofa",
    "corn": "maíz",
    "peas": "guisante",
    "green bean": "judía verde",
    "mushroom": "champiñón",
    "pineapple": "piña",
    "banana": "plátano",
    "apple": "manzana",
    "pear": "pera",
    "peach": "melocotón",
    "nectarine": "melocotón",
    "plum": "ciruela",
    "cherry": "cereza",
    "grape": "uva",
    "watermelon": "sandía",
    "melon": "melón",
    "strawberry": "fresa",
    "blueberry": "arándano",
    "raspberry": "frambuesa",
    "blackberry": "mora",
    "mango": "mango",
    "papaya": "papaya",
    "coconut": "coco",
    "lemon": "limón",
    "lime": "lima",
    "orange": "naranja",
    "grapefruit": "pomelo",
    "tangerine": "mandarina",
    "pomegranate": "granada",
    "fig": "higo",
    "date fruit": "dátil",
    "almond": "almendra",
    "walnut": "nuez",
    "hazelnut": "avellana",
    "peanut": "cacahuete",
    "cashew": "anacardo",
    "pistachio": "pistacho",
    "chestnut": "castaña",
    "pecan": "pecana",
    "olive": "aceituna",
    "olive oil": "aceite de oliva",
    "vegetable oil": "aceite",
    "sunflower oil": "aceite",
    "flour": "harina",
    "wheat flour": "harina",
    "sugar": "azúcar",
    "white sugar": "azúcar",
    "brown sugar": "azúcar",
    "salt": "sal",
    "sea salt": "sal",
    "black pepper": "pimienta",
    "pepper": "pimienta",
    "cinnamon": "canela",
    "paprika": "pimentón",
    "turmeric": "cúrcuma",
    "ginger": "jengibre",
    "saffron": "azafrán",
    "bay leaf": "laurel",
    "oregano": "orégano",
    "thyme": "tomillo",
    "rosemary": "romero",
    "basil": "albahaca",
    "parsley": "perejil",
    "cilantro": "cilantro",
    "dill": "eneldo",
    "mint": "menta",
    "vanilla": "vainilla",
    "cocoa": "cacao",
    "coffee": "café",
    "tea": "té",
    "beer": "cerveza",
    "wine": "vino",
    "red wine": "vino",
    "white wine": "vino",
    "bread": "pan",
    "white bread": "pan",
    "whole wheat bread": "pan",
    "toast": "pan tostado",
    "pita": "pan de pita",
    "tortilla": "tortilla",
    "ham": "jamón",
    "bacon": "tocino",
    "salami": "salchichón",
    "chorizo": "chorizo",
    "hot dog": "salchicha",
    "hamburger": "hamburguesa",
    "steak": "filete",
    "roast beef": "carne asada",
    "pork chop": "chuleta de cerdo",
    "chicken wing": "ala de pollo",
    "chicken leg": "muslo de pollo",
    "turkey": "pavo",
    "yogurt": "yogur",
    "ice cream": "helado",
    "cake": "pastel",
    "cookie": "galleta",
    "biscuit": "galleta",
    "muffin": "magdalena",
    "pancake": "panqueque",
    "waffle": "gofre",
    "donut": "dona",
    "pie": "tarta",
    "cheesecake": "tarta de queso",
    "pudding": "pudín",
    "custard": "natillas",
    "jelly": "gelatina",
    "jam": "mermelada",
    "honey": "miel",
    "maple syrup": "sirope de arce",
    "chocolate sauce": "chocolate",
    "mayonnaise": "mayonesa",
    "mustard": "mostaza",
    "ketchup": "kétchup",
    "vinegar": "vinagre",
    "soy sauce": "salsa de soja",
    "rice": "arroz",
    "pasta": "pasta",
    "spaghetti": "pasta",
    "macaroni": "pasta",
    "noodle": "fideo",
    "lasagna": "pasta",
    "ravioli": "pasta",
    "pizza": "pizza",
    "soup": "sopa",
    "salad": "ensalada",
    "sandwich": "sándwich",
    "taco": "taco",
    "burrito": "burrito",
    "quesadilla": "quesadilla",
    "guacamole": "guacamole",
    "salsa": "salsa",
}

# Generic labels that are too broad to map to any ingredient
GENERIC_LABELS = {
    "food", "ingredient", "produce", "grocery", "supermarket",
    "dish", "meal", "cuisine", "recipe", "cooking", "baking",
    "kitchen", "table", "plate", "bowl", "cutting board",
    "breakfast", "lunch", "dinner", "snack", "appetizer",
    "side dish", "main course", "dessert", "drink",
}

# Spanish words for OCR filtering — common words that appear on food packages
SPANISH_WORDS = {
    "aceite", "aceituna", "agua", "ajo", "albahaca", "alcachofa", "almendra",
    "anacardo", "apio", "arándano", "arroz", "atún", "avellana", "avena",
    "azúcar", "azafrán", "bacalao", "berenjena", "boniato", "brócoli",
    "cacahuete", "café", "calabacín", "calabaza", "camarón", "canela",
    "carne", "caracol", "caramelo", "castaña", "cebolla", "cerdo", "cereza",
    "cerveza", "chalote", "champiñón", "chile", "chirimoya", "chocolate",
    "chorizo", "chuleta", "cilantro", "ciruela", "coco", "coliflor",
    "col", "cordero", "crema", "cúrcuma", "dátil", "dona", "durian",
    "eneldo", "ensalada", "espárrago", "espinaca", "esturión", "fideo",
    "filete", "frambuesa", "fresa", "frijol", "galleta", "garbanzo",
    "gelatina", "gofre", "granada", "guacamole", "guisante", "haba",
    "hamburguesa", "harina", "helado", "higo", "huevo", "jamón", "jengibre",
    "judía", "langosta", "laurel", "leche", "lechuga", "legumbre",
    "lenteja", "lichi", "lima", "limón", "lubina", "magdalena", "maíz",
    "mandarina", "mango", "mantequilla", "manzana", "maracuyá", "mayonesa",
    "mejillón", "melocotón", "melón", "menta", "mermelada", "miel",
    "mora", "mostaza", "muslo", "naranja", "natillas", "nuez", "orégano",
    "ostra", "pan", "panqueque", "papaya", "paprika", "pasta", "pastel",
    "patata", "pato", "pavo", "pecana", "pechuga", "pepino", "pepinillo",
    "pera", "perejil", "perrito", "pescado", "pimienta", "pimiento",
    "piña", "piñón", "pistacho", "pizza", "plátano", "pollo", "pomelo",
    "pretzel", "pudín", "puerro", "puré", "quesadilla", "queso", "rábano",
    "repollo", "res", "romero", "rúcula", "sal", "salchicha", "salchichón",
    "salmón", "salsa", "sandía", "sándwich", "sardina", "soja", "sopa",
    "taco", "tarta", "té", "tocino", "tomate", "tomillo", "tortilla",
    "trucha", "tuna", "uva", "vainilla", "vino", "vinagre", "yaca",
    "yogur", "zanahoria", "aceite", "harina", "levadura", "polvo",
    "gurullos", "aneto", "buey", "lomo", "contramuslo", "ramillete",
}


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        _api_key = os.environ.get("GOOGLE_VISION_API_KEY", "")
    return _api_key


def is_available() -> bool:
    return bool(_get_api_key())


def _annotate(image_bytes: bytes, features: list[dict]) -> dict:
    """Make a raw request to Google Vision REST API."""
    key = _get_api_key()
    if not key:
        return None

    encoded = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": features,
            }
        ]
    }

    resp = requests.post(
        f"{API_URL}?key={key}",
        json=payload,
        timeout=30,
    )

    if resp.status_code != 200:
        logger.error("Google Vision API error %s: %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    responses = data.get("responses", [])
    if not responses:
        return None

    error = responses[0].get("error")
    if error:
        logger.error("Google Vision API error: %s", error.get("message", error))
        return None

    return responses[0]


def _match_label_to_ingredient(desc: str) -> str:
    """Try to match a Google Vision label to an ingredient name."""
    desc_lower = desc.lower().strip()

    # 0. Skip non-food
    if any(w in desc_lower for w in NON_FOOD_WORDS):
        return None

    # 1. Skip generic food labels (too broad)
    if desc_lower in GENERIC_LABELS:
        return None

    # 2. Exact match in FOOD_MAP (original case from ImageNet)
    ing = FOOD_MAP.get(desc)
    if ing:
        return ing

    # 3. Exact match in GV_FOOD_MAP
    ing = GV_FOOD_MAP.get(desc_lower)
    if ing:
        return ing

    # 4. Case-insensitive match in FOOD_MAP
    for k, v in FOOD_MAP.items():
        if k.lower() == desc_lower:
            return v

    # 5. Substring match: label contains a FOOD_MAP key or vice versa
    for k, v in FOOD_MAP.items():
        kl = k.lower()
        if len(kl) > 3 and (kl in desc_lower or desc_lower in kl):
            return v

    # 6. Substring match in GV_FOOD_MAP
    for k, v in GV_FOOD_MAP.items():
        if len(k) > 3 and (k in desc_lower or desc_lower in k):
            return v

    # 7. Word-level match: a word in desc matches a FOOD_MAP key
    desc_words = set(re.findall(r"[a-záéíóúüñ]+", desc_lower))
    for k, v in FOOD_MAP.items():
        kl = k.lower()
        if len(kl) > 3 and kl in desc_words:
            return v

    return None


def detect_labels(image_bytes: bytes, top_k: int = 20) -> list:
    """Detect labels and map to ingredient names."""
    result = _annotate(image_bytes, [{"type": "LABEL_DETECTION", "maxResults": top_k}])
    if result is None:
        return None

    labels = result.get("labelAnnotations", [])
    results = []
    seen = set()
    for label in labels:
        desc = label.get("description", "")
        score = label.get("score", 0)
        ing = _match_label_to_ingredient(desc)
        if ing and ing not in seen:
            seen.add(ing)
            results.append((ing, score))

    results.sort(key=lambda x: -x[1])
    return results[:10]


def detect_objects(image_bytes: bytes) -> list:
    """Use Object Localization to find specific objects in the image."""
    result = _annotate(image_bytes, [{"type": "OBJECT_LOCALIZATION", "maxResults": 10}])
    if result is None:
        return None

    objs = result.get("localizedObjectAnnotations", [])
    results = []
    seen = set()
    for obj in objs:
        name = obj.get("name", "")
        score = obj.get("score", 0)
        ing = _match_label_to_ingredient(name)
        if ing and ing not in seen:
            seen.add(ing)
            results.append((ing, score))

    results.sort(key=lambda x: -x[1])
    return results


def detect_text(image_bytes: bytes) -> str:
    """Extract text from image using Google Vision OCR."""
    result = _annotate(image_bytes, [
        {"type": "TEXT_DETECTION"},
    ])
    if result is None:
        return None

    annotations = result.get("textAnnotations", [])
    if annotations:
        return annotations[0].get("description", "")
    return ""


def detect_web_entities(image_bytes: bytes) -> list:
    """Detect web entities related to the image."""
    result = _annotate(image_bytes, [{"type": "WEB_DETECTION", "maxResults": 10}])
    if result is None:
        return None

    web = result.get("webDetection", {})
    entities = web.get("webEntities", [])
    results = []
    seen = set()
    for e in entities:
        desc = e.get("description", "")
        score = e.get("score", 0)
        if score > 0.5:
            ing = _match_label_to_ingredient(desc)
            if ing and ing not in seen:
                seen.add(ing)
                results.append((ing, score))
    return results


def detect_all(image_bytes: bytes, with_text: bool = False) -> tuple:
    """Run visual detection, return (visual_results, ocr_text).
    By default only visual (labels + objects + web). Set with_text=True to also run OCR."""
    features = [
        {"type": "LABEL_DETECTION", "maxResults": 20},
        {"type": "OBJECT_LOCALIZATION", "maxResults": 10},
        {"type": "WEB_DETECTION", "maxResults": 10},
    ]
    if with_text:
        features.append({"type": "TEXT_DETECTION"})

    result = _annotate(image_bytes, features)
    if result is None:
        return None, None

    visual = []
    seen = set()

    # Labels
    for label in result.get("labelAnnotations", []):
        desc = label.get("description", "")
        score = label.get("score", 0)
        ing = _match_label_to_ingredient(desc)
        if ing and ing not in seen:
            seen.add(ing)
            visual.append((ing, score))

    # Objects (higher specificity, boost score)
    for obj in result.get("localizedObjectAnnotations", []):
        name = obj.get("name", "")
        score = obj.get("score", 0)
        ing = _match_label_to_ingredient(name)
        if ing:
            new_score = min(1.0, score * 1.0)
            if ing not in seen:
                seen.add(ing)
                visual.append((ing, new_score))
            else:
                for i, (existing, old_s) in enumerate(visual):
                    if existing == ing and new_score > old_s:
                        visual[i] = (ing, new_score)

    # Web entities (lower confidence boost)
    web = result.get("webDetection", {})
    for e in web.get("webEntities", []):
        desc = e.get("description", "")
        score = e.get("score", 0)
        if score > 0.5:
            ing = _match_label_to_ingredient(desc)
            if ing and ing not in seen:
                seen.add(ing)
                visual.append((ing, score * 0.85))

    visual.sort(key=lambda x: -x[1])

    # OCR text (only if requested)
    text = ""
    if with_text:
        annotations = result.get("textAnnotations", [])
        if annotations:
            text = annotations[0].get("description", "")

    return visual[:10], text
