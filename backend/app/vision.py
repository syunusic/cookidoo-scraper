import io
from pathlib import Path

import numpy as np
import tensorflow as tf
from PIL import Image

# ImageNet food classes → ingredient names
FOOD_MAP = {
    "Granny Smith": "manzana verde",
    "pineapple": "piña",
    "banana": "plátano",
    "lemon": "limón",
    "orange": "naranja",
    "strawberry": "fresa",
    "watermelon": "sandía",
    "grape": "uva",
    "cherry": "cereza",
    "pear": "pera",
    "peach": "melocotón",
    "apple": "manzana",
    "sweet pepper": "pimiento",
    "bell pepper": "pimiento",
    "cucumber": "pepino",
    "cucumber, pickled": "pepinillo",
    "artichoke": "alcachofa",
    "broccoli": "brócoli",
    "cauliflower": "coliflor",
    "zucchini": "calabacín",
    "butternut squash": "calabaza",
    "acorn squash": "calabaza",
    "spaghetti squash": "calabaza",
    "mushroom": "champiñón",
    "mushroom, agaric": "champiñón",
    "corn": "maíz",
    "ear of corn": "maíz",
    "carrot": "zanahoria",
    "asparagus": "espárrago",
    "celery": "apio",
    "radish": "rábano",
    "tomato": "tomate",
    "eggplant": "berenjena",
    "cabbage": "repollo",
    "cauliflower": "coliflor",
    "brussels sprout": "col de Bruselas",
    "kale": "col rizada",
    "spinach": "espinaca",
    "lettuce": "lechuga",
    "head lettuce": "lechuga",
    "onion": "cebolla",
    "garlic": "ajo",
    "shallot": "chalote",
    "leek": "puerro",
    "potato": "patata",
    "sweet potato": "boniato",
    "egg": "huevo",
    "bagel": "pan",
    "bread": "pan",
    "French loaf": "pan",
    "loaf": "pan",
    "bakery": "pan",
    "cheese": "queso",
    "cheeseburger": "hamburguesa",
    "hamburger": "hamburguesa",
    "pizza": "pizza",
    "avocado": "aguacate",
    "coconut": "coco",
    "fig": "higo",
    "pomegranate": "granada",
    "mango": "mango",
    "papaya": "papaya",
    "cantaloupe": "melón",
    "honeydew": "melón",
    "jackfruit": "yaca",
    "custard apple": "chirimoya",
    "durian": "durian",
    "passion fruit": "maracuyá",
    "lychee": "lichi",
    "date": "dátil",
    "rapeseed": "aceite",
    "peanut": "cacahuete",
    "walnut": "nuez",
    "hazelnut": "avellana",
    "chestnut": "castaña",
    "acorn": "bellota",
    "pecan": "pecana",
    "almond": "almendra",
    "cashew": "anacardo",
    "pistachio": "pistacho",
    "pine nut": "piñón",
    "soy": "soja",
    "kidney bean": "frijol",
    "lima bean": "haba",
    "green bean": "judía verde",
    "chickpea": "garbanzo",
    "lentil": "lenteja",
    "rice": "arroz",
    "pasta": "pasta",
    "spaghetti": "pasta",
    "spaghetti squash": "calabaza",
    "butter": "mantequilla",
    "yogurt": "yogur",
    "ice cream": "helado",
    "chocolate": "chocolate",
    "cookie": "galleta",
    "muffin": "magdalena",
    "cupcake": "magdalena",
    "candy": "caramelo",
    "lollipop": "caramelo",
    "pretzel": "pretzel",
    "popcorn": "palomitas",
    "sandwich": "sándwich",
    "hotdog": "perrito caliente",
    "burrito": "burrito",
    "taco": "taco",
    "enchilada": "enchilada",
    "quesadilla": "quesadilla",
    "guacamole": "guacamole",
    "soup": "sopa",
    "salad": "ensalada",
    "french fries": "patatas fritas",
    "mashed potato": "puré de patata",
    "meat loaf": "pastel de carne",
    "roast chicken": "pollo asado",
    "drumstick": "muslo de pollo",
    "chicken leg": "muslo de pollo",
    "chicken wing": "ala de pollo",
    "pork chop": "chuleta de cerdo",
    "bacon": "tocino",
    "ham": "jamón",
    "sausage": "salchicha",
    "salmon": "salmón",
    "trout": "trucha",
    "sea bass": "lubina",
    "sturgeon": "esturión",
    "eel": "anguila",
    "crab": "cangrejo",
    "lobster": "langosta",
    "shrimp": "camarón",
    "snail": "caracol",
    "mussel": "mejillón",
    "oyster": "ostra",
    "tuna": "atún",
    "cod": "bacalao",
    "herring": "arenque",
    "sardine": "sardina",
    "milk": "leche",
    "coffee": "café",
    "tea": "té",
    "beer": "cerveza",
    "red wine": "vino",
}

# ImageNet non-food class names that we should skip
NON_FOOD_WORDS = {
    "dog", "cat", "bird", "car", "bicycle", "motorcycle", "airplane",
    "boat", "train", "truck", "bus", "chair", "table", "sofa", "bed",
    "lamp", "clock", "phone", "computer", "keyboard", "mouse", "tv",
    "remote", "book", "magazine", "newspaper", "person", "man", "woman",
    "child", "baby", "hand", "foot", "face", "eye", "nose", "ear",
    "shirt", "pants", "shorts", "dress", "skirt", "jacket", "coat",
    "hat", "shoe", "sock", "glove", "scarf", "tie", "belt", "bag",
    "backpack", "purse", "umbrella", "ball", "balloon", "kite",
    "frisbee", "racket", "bat", "glider", "parachute", "bottle",
    "cup", "glass", "plate", "bowl", "spoon", "fork", "knife",
    "furniture", "tool", "weapon", "machine", "engine", "motor",
    "wheel", "tire", "piano", "guitar", "violin", "flute", "drum",
    "camera", "microphone", "headphone", "speaker", "printer",
    "scanner", "fan", "heater", "air conditioner", "refrigerator",
    "stove", "oven", "microwave", "dishwasher", "washer", "dryer",
    "toilet", "sink", "bathtub", "shower", "curtain", "pillow",
    "blanket", "towel", "rug", "mat", "door", "window", "floor",
    "wall", "ceiling", "stairs", "fence", "gate", "bridge", "building",
    "house", "castle", "church", "temple", "skyscraper", "tower",
    "flag", "sign", "screen", "monitor", "display",
}

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = tf.keras.applications.MobileNetV2(weights="imagenet", input_shape=(224, 224, 3))
    return _model


def classify_image(image_bytes: bytes, top_k: int = 5):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((224, 224))
    arr = tf.keras.preprocessing.image.img_to_array(img)
    arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
    arr = np.expand_dims(arr, axis=0)

    model = _get_model()
    preds = model.predict(arr, verbose=0)
    decoded = tf.keras.applications.mobilenet_v2.decode_predictions(preds, top=top_k)[0]

    results = []
    for _, class_name, score in decoded:
        class_lower = class_name.lower()
        if any(word in class_lower for word in NON_FOOD_WORDS):
            continue
        ingredient = FOOD_MAP.get(class_name)
        if ingredient:
            results.append((ingredient, float(score)))

    return results
