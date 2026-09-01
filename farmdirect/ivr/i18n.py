"""Bilingual IVR prompt strings (Tamil + English).

The Tamil terminology matches the FarmDirect application's existing vocabulary
(விளைபொருள் / சந்தை விலை / ஆர்டர் / டெலிவரி / வருமானம் / தரம்).
Every prompt has both a ``ta`` and an ``en`` form so the dialog manager can
serve either language on the same call without reloading.
"""
from typing import Dict

# --------------------------------------------------------------------- Welcome
WELCOME = {
    "ta": [
        "வணக்கம். உழவர் நேரடி சேவைக்கு வரவேற்கிறோம்.",
        "தமிழில் தொடர 1 அழுத்தவும்.",
        "English-க்கு 2 அழுத்தவும்.",
    ],
    "en": [
        "Welcome to Uzhavar Direct.",
        "Press 1 for Tamil.",
        "Press 2 for English.",
    ],
}

# --------------------------------------------------------------------- Main menu
MAIN_MENU = {
    "ta": [
        "வணக்கம். உழவர் நேரடி குரல் சேவைக்கு வரவேற்கிறோம்.",
        "விளைபொருளை விற்பனைக்கு பதிவு செய்ய 1 அழுத்தவும்.",
        "இன்றைய சந்தை விலையை அறிய 2 அழுத்தவும்.",
        "எனது ஆர்டர்களை அறிய 3 அழுத்தவும்.",
        "டெலிவரி நிலையை அறிய 4 அழுத்தவும்.",
        "மொத்த ஆர்டர் வாய்ப்புகளை அறிய 5 அழுத்தவும்.",
        "எனது வருமானத்தை அறிய 6 அழுத்தவும்.",
        "உதவிக்கு 7 அழுத்தவும்.",
        "மொழியை மாற்ற 8 அழுத்தவும்.",
    ],
    "en": [
        "Welcome to Uzhavar Direct voice service.",
        "To list your produce for sale, press 1.",
        "To hear today's market price, press 2.",
        "To check your orders, press 3.",
        "To check delivery status, press 4.",
        "To check bulk order opportunities, press 5.",
        "To check your earnings, press 6.",
        "For help, press 7.",
        "To change language, press 8.",
    ],
}

# --------------------------------------------------------------------- Help
HELP_TEXT = {
    "ta": [
        "இந்த சேவை உங்கள் விளைபொருளை நேரடியாக வாடிக்கையாளர்களுக்கு விற்க உதவுகிறது.",
        "நீங்கள் குரலில் அல்லது விசைகள் மூலம் பேசலாம்.",
        "உதாரணம்: என்னிடம் நூறு கிலோ தக்காளி இருக்கு.",
        "முக்கிய மெனுவுக்கு திரும்ப 0 அழுத்தவும்.",
    ],
    "en": [
        "This service lets you sell your produce directly to buyers.",
        "You can speak naturally or use the keypad.",
        "For example: I have one hundred kilos of tomatoes.",
        "Press 0 to return to the main menu.",
    ],
}

# --------------------------------------------------------------------- Errors
ERRORS = {
    "speech_unclear_1": {
        "ta": "மன்னிக்கவும். மீண்டும் சொல்லுங்கள்.",
        "en": "Sorry, I didn't catch that. Could you say it again?",
    },
    "speech_unclear_2": {
        "ta": "உங்கள் பதிலை எளிதாக சொல்லுங்கள்.",
        "en": "Please speak your answer a little more simply.",
    },
    "speech_unclear_3": {
        "ta": "குரல் மூலம் புரிந்து கொள்ள முடியவில்லை. தொலைபேசி விசைகளை பயன்படுத்தலாம்.",
        "en": "I still can't understand your voice. You can use the keypad instead.",
    },
    "invalid_choice": {
        "ta": "தவறான தேர்வு. மீண்டும் முயற்சிக்கவும்.",
        "en": "Invalid choice. Please try again.",
    },
    "no_account": {
        "ta": "இந்த தொலைபேசி எண்ணில் உழவர் நேரடி கணக்கு இல்லை. கணக்கு உருவாக்க உதவிக்கு 7 அழுத்தவும்.",
        "en": "There is no Uzhavar Direct account for this phone number. Press 7 for help creating an account.",
    },
    "no_orders": {
        "ta": "உங்களுக்கு தற்போது ஆர்டர்கள் இல்லை.",
        "en": "You have no orders at this time.",
    },
    "no_listings": {
        "ta": "உங்களுக்கு தற்போது விற்பனைக்கான விளைபொருள் இல்லை.",
        "en": "You have no produce listed for sale.",
    },
    "no_bulk": {
        "ta": "உங்கள் பகுதியில் தற்போது மொத்த ஆர்டர் வாய்ப்புகள் இல்லை.",
        "en": "There are no bulk order opportunities in your area right now.",
    },
    "product_unknown": {
        "ta": "நீங்கள் கூறிய விளைபொருள் புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
        "en": "I didn't recognise that produce. Please say it again.",
    },
    "quantity_missing": {
        "ta": "எவ்வளவு அளவு என்பதை கூறுங்கள். உதாரணம்: நூறு கிலோ.",
        "en": "Please tell me the quantity, for example: one hundred kilos.",
    },
    "price_missing": {
        "ta": "ஒரு கிலோவுக்கு எவ்வளவு விலை என்பதை கூறுங்கள். உதாரணம்: முப்பத்து எட்டு ரூபாய்.",
        "en": "Please tell me the price per kilo, for example: thirty eight rupees.",
    },
    "db_unavailable": {
        "ta": "இப்போது சேவை இயங்கவில்லை. சிறிது நேரம் கழித்து மீண்டும் அழைக்கவும்.",
        "en": "The service is temporarily unavailable. Please call back shortly.",
    },
}

# --------------------------------------------------------------------- Prompts
PROMPTS: Dict[str, Dict[str, str]] = {
    # Listing flow
    "list_ask_crop": {
        "ta": "எந்த விளைபொருளை விற்க விரும்புகிறீர்கள்? உதாரணம்: தக்காளி, வெங்காயம், உருளைக்கிழங்கு.",
        "en": "What produce would you like to sell? For example: tomato, onion, potato.",
    },
    "list_ask_qty": {
        "ta": "எவ்வளவு அளவு இருக்கிறது? உதாரணம்: நூறு கிலோ.",
        "en": "How much do you have? For example: one hundred kilos.",
    },
    "list_ask_price": {
        "ta": "ஒரு கிலோவுக்கு எவ்வளவு விலை எதிர்பார்க்கிறீர்கள்?",
        "en": "What price do you expect per kilo?",
    },
    "list_ask_harvest": {
        "ta": "இந்த விளைபொருள் எப்போது அறுவடை செய்யப்பட்டது? இன்று, நேற்று அல்லது தேதி சொல்லுங்கள்.",
        "en": "When was this harvested? Today, yesterday, or a date.",
    },
    "list_ask_grade": {
        "ta": "தரத்தை தேர்வு செய்யுங்கள். A+க்கு 1, Aக்கு 2, Bக்கு 3.",
        "en": "Select the quality grade. Press 1 for A+, 2 for A, 3 for B.",
    },
    "list_summary": {
        "ta": "நீங்கள் {qty} கிலோ {crop} ஒரு கிலோ {price} ரூபாய் விலையில், {grade} தரத்தில், {harvest_label} அறுவடை செய்ததாக பதிவு செய்துள்ளீர்கள்.",
        "en": "You are listing {qty} kg of {crop} at {price} rupees per kg, {grade} grade, harvested {harvest_label}.",
    },
    "list_confirm_options": {
        "ta": "பதிவு செய்ய 1 அழுத்தவும். மாற்ற 2 அழுத்தவும். ரத்து செய்ய 3 அழுத்தவும்.",
        "en": "Press 1 to confirm. Press 2 to change. Press 3 to cancel.",
    },
    "list_success": {
        "ta": "உங்கள் விளைபொருள் வெற்றிகரமாக பதிவு செய்யப்பட்டது.",
        "en": "Your produce has been listed successfully.",
    },
    "list_cancelled": {
        "ta": "பதிவு ரத்து செய்யப்பட்டது.",
        "en": "Listing cancelled.",
    },
    # AI price hint
    "price_hint_offer": {
        "ta": "நீங்கள் பதிவு செய்த விலை கிலோவுக்கு {price} ரூபாய். தற்போதைய சந்தை விலை சுமார் {low} முதல் {high} ரூபாய். AI பரிந்துரையை கேட்க 1 அழுத்தவும்.",
        "en": "You entered {price} rupees per kg. The current market range is about {low} to {high} rupees. Press 1 to hear the AI recommendation.",
    },
    "price_hint_recommend": {
        "ta": "AI பரிந்துரை: கிலோவுக்கு {suggested} ரூபாய். உங்கள் விலையை இதற்கு மாற்ற 1 அழுத்தவும், அல்லது உங்கள் விலையை வைத்துக்கொள்ள 2 அழுத்தவும்.",
        "en": "AI recommends {suggested} rupees per kg. Press 1 to use this price, or 2 to keep your price.",
    },
    "price_hint_skipped": {
        "ta": "சரி, உங்கள் விலையே பதிவு செய்யப்படும்.",
        "en": "OK, your price will be used.",
    },
    # Market price
    "price_ask_crop": {
        "ta": "எந்த விளைபொருளின் விலையை அறிய விரும்புகிறீர்கள்?",
        "en": "Which produce price would you like to hear?",
    },
    "price_report": {
        "ta": "இன்று {crop} சந்தை விலை கிலோவுக்கு {low} முதல் {high} ரூபாய் வரை உள்ளது. சராசரி விலை {avg} ரூபாய். இந்த தகவல் {updated} அன்று புதுப்பிக்கப்பட்டது.",
        "en": "Today {crop} market price is between {low} and {high} rupees per kg. Average price is {avg} rupees. This information was updated on {updated}.",
    },
    "price_unavailable": {
        "ta": "தற்போது {crop} விலை தகவல் கிடைக்கவில்லை.",
        "en": "Market price for {crop} is not available right now.",
    },
    "demo_note": {
        "ta": "குறிப்பு: இந்த சந்தை விலை முன்னோட்ட தரவின் அடிப்படையில் உள்ளது.",
        "en": "Note: this market price is based on demo data.",
    },
    # Orders
    "order_latest": {
        "ta": "உங்கள் சமீபத்திய ஆர்டர் எண் {code}. தற்போதைய நிலை: {status}.",
        "en": "Your latest order is {code}. Current status: {status}.",
    },
    "order_more": {
        "ta": "மற்ற ஆர்டர்களை கேட்க 1 அழுத்தவும்.",
        "en": "Press 1 to hear other orders.",
    },
    # Delivery
    "delivery_report": {
        "ta": "ஆர்டர் {code} டெலிவரி நிலை: {status}. {extra}",
        "en": "Order {code} delivery status: {status}. {extra}",
    },
    # Bulk
    "bulk_report": {
        "ta": "உங்கள் பகுதியில் {qty} கிலோ {crop}க்கு ஒரு மொத்த ஆர்டர் உள்ளது. உங்கள் தற்போதைய இருப்பில் இருந்து {avail} கிலோ வரை வழங்கலாம். இந்த வாய்ப்பை ஏற்க 1 அழுத்தவும். வேண்டாம் என்றால் 2 அழுத்தவும்.",
        "en": "There is a bulk order in your area for {qty} kg of {crop}. You can supply up to {avail} kg from your current listings. Press 1 to accept. Press 2 to decline.",
    },
    "bulk_accept_ok": {
        "ta": "மொத்த ஆர்டர் ஏற்கப்பட்டது. விற்பனையாளர் சிறிது நேரத்தில் உங்களை தொடர்பு கொள்வார்.",
        "en": "Bulk order accepted. The buyer will contact you shortly.",
    },
    "bulk_declined": {
        "ta": "சரி, இந்த வாய்ப்பு தவிர்க்கப்பட்டது.",
        "en": "OK, this opportunity has been skipped.",
    },
    # Earnings
    "earnings_report": {
        "ta": "இன்று வருமானம் {today} ரூபாய். இந்த வாரம் {week} ரூபாய். இந்த மாதம் {month} ரூபாய். பெறப்பட்டது {paid} ரூபாய். நிலுவையில் {pending} ரூபாய்.",
        "en": "Today's earnings: {today} rupees. This week: {week} rupees. This month: {month} rupees. Paid: {paid} rupees. Pending: {pending} rupees.",
    },
    # Misc
    "returning_to_main": {
        "ta": "முக்கிய மெனுவுக்கு திரும்புகிறோம்.",
        "en": "Returning to the main menu.",
    },
    "goodbye": {
        "ta": "நன்றி. உழவர் நேரடி சேவையை பயன்படுத்தியதற்கு நன்றி. வணக்கம்.",
        "en": "Thank you for using Uzhavar Direct. Goodbye.",
    },
    "acknowledged": {
        "ta": "சரி.",
        "en": "OK.",
    },
}


def pick_prompt(key: str, lang: str, **fmt) -> str:
    """Return the prompt for ``key`` in ``lang``, formatted with ``**fmt``."""
    entry = PROMPTS.get(key) or ERRORS.get(key) or {}
    txt = entry.get(lang) or entry.get("en") or entry.get("ta") or ""
    try:
        return txt.format(**fmt) if fmt else txt
    except (KeyError, IndexError):
        return txt
