"""
Language Service for Hampstead Renovations Voice AI Agent

Multi-language support with:
- Language detection from text and voice
- Translation for Polish, Spanish, French, Arabic, Portuguese
- Context-aware responses in customer's preferred language
- Seamless handoff to human translators for complex cases
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

import anthropic
from config import settings

logger = logging.getLogger(__name__)


class SupportedLanguage(Enum):
    """Languages supported by the system"""

    ENGLISH = "en"
    POLISH = "pl"
    SPANISH = "es"
    FRENCH = "fr"
    ARABIC = "ar"
    PORTUGUESE = "pt"
    HINDI = "hi"
    BENGALI = "bn"
    URDU = "ur"
    TURKISH = "tr"


@dataclass
class LanguageDetectionResult:
    """Result of language detection"""

    detected_language: SupportedLanguage
    confidence: float
    original_text: str
    is_mixed_language: bool = False
    secondary_language: SupportedLanguage | None = None


@dataclass
class TranslationResult:
    """Result of translation"""

    original_text: str
    translated_text: str
    source_language: SupportedLanguage
    target_language: SupportedLanguage
    confidence: float


@dataclass
class LanguagePreference:
    """User's language preference"""

    user_id: str
    preferred_language: SupportedLanguage
    detected_languages: list[SupportedLanguage] = field(default_factory=list)
    auto_translate: bool = True


class LanguageService:
    """
    Multi-language support service

    Provides:
    - Language detection from text
    - Translation using Claude (with cultural context)
    - Language preference management
    - Localized greeting templates
    """

    # Greetings in different languages
    GREETINGS = {
        SupportedLanguage.ENGLISH: "Hello! Thank you for contacting Hampstead Renovations. How can I help you today?",
        SupportedLanguage.POLISH: "Dzień dobry! Dziękujemy za kontakt z Hampstead Renovations. W czym mogę pomóc?",
        SupportedLanguage.SPANISH: "¡Hola! Gracias por contactar a Hampstead Renovations. ¿En qué puedo ayudarle hoy?",
        SupportedLanguage.FRENCH: "Bonjour! Merci d'avoir contacté Hampstead Renovations. Comment puis-je vous aider aujourd'hui?",
        SupportedLanguage.ARABIC: "مرحباً! شكراً لتواصلك مع Hampstead Renovations. كيف يمكنني مساعدتك اليوم؟",
        SupportedLanguage.PORTUGUESE: "Olá! Obrigado por contactar a Hampstead Renovations. Como posso ajudá-lo hoje?",
        SupportedLanguage.HINDI: "नमस्ते! Hampstead Renovations से संपर्क करने के लिए धन्यवाद। मैं आज आपकी कैसे मदद कर सकता हूं?",
        SupportedLanguage.BENGALI: "হ্যালো! Hampstead Renovations-এ যোগাযোগ করার জন্য ধন্যবাদ। আজ আমি কীভাবে আপনাকে সাহায্য করতে পারি?",
        SupportedLanguage.URDU: "سلام! Hampstead Renovations سے رابطہ کرنے کا شکریہ۔ میں آج آپ کی کیسے مدد کر سکتا ہوں؟",
        SupportedLanguage.TURKISH: "Merhaba! Hampstead Renovations ile iletişime geçtiğiniz için teşekkürler. Bugün size nasıl yardımcı olabilirim?",
    }

    # Common renovation terms translations
    RENOVATION_TERMS = {
        "kitchen": {
            SupportedLanguage.POLISH: "kuchnia",
            SupportedLanguage.SPANISH: "cocina",
            SupportedLanguage.FRENCH: "cuisine",
            SupportedLanguage.ARABIC: "مطبخ",
            SupportedLanguage.PORTUGUESE: "cozinha",
        },
        "bathroom": {
            SupportedLanguage.POLISH: "łazienka",
            SupportedLanguage.SPANISH: "baño",
            SupportedLanguage.FRENCH: "salle de bain",
            SupportedLanguage.ARABIC: "حمام",
            SupportedLanguage.PORTUGUESE: "banheiro",
        },
        "extension": {
            SupportedLanguage.POLISH: "rozbudowa",
            SupportedLanguage.SPANISH: "extensión",
            SupportedLanguage.FRENCH: "extension",
            SupportedLanguage.ARABIC: "توسعة",
            SupportedLanguage.PORTUGUESE: "extensão",
        },
        "loft conversion": {
            SupportedLanguage.POLISH: "adaptacja poddasza",
            SupportedLanguage.SPANISH: "conversión de ático",
            SupportedLanguage.FRENCH: "aménagement de combles",
            SupportedLanguage.ARABIC: "تحويل العلية",
            SupportedLanguage.PORTUGUESE: "conversão de sótão",
        },
        "renovation": {
            SupportedLanguage.POLISH: "remont",
            SupportedLanguage.SPANISH: "renovación",
            SupportedLanguage.FRENCH: "rénovation",
            SupportedLanguage.ARABIC: "تجديد",
            SupportedLanguage.PORTUGUESE: "renovação",
        },
    }

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"
        self._user_preferences: dict[str, LanguagePreference] = {}

    async def detect_language(self, text: str) -> LanguageDetectionResult:
        """
        Detect the language of input text

        Args:
            text: Input text to analyze

        Returns:
            LanguageDetectionResult with detected language and confidence
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                system="You are a language detection expert. Analyze the given text and identify the primary language. Return JSON only.",
                messages=[
                    {
                        "role": "user",
                        "content": f"""Detect the language of this text: "{text}"

Return JSON:
{{
    "language_code": "en|pl|es|fr|ar|pt|hi|bn|ur|tr",
    "confidence": 0.0-1.0,
    "is_mixed": true/false,
    "secondary_language": "code or null"
}}""",
                    }
                ],
            )

            result = json.loads(response.content[0].text)

            lang_code = result.get("language_code", "en")
            lang_map = {lang.value: lang for lang in SupportedLanguage}
            detected = lang_map.get(lang_code, SupportedLanguage.ENGLISH)

            secondary = None
            if result.get("secondary_language"):
                secondary = lang_map.get(result["secondary_language"])

            return LanguageDetectionResult(
                detected_language=detected,
                confidence=result.get("confidence", 0.5),
                original_text=text,
                is_mixed_language=result.get("is_mixed", False),
                secondary_language=secondary,
            )

        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            # Default to English with low confidence
            return LanguageDetectionResult(
                detected_language=SupportedLanguage.ENGLISH,
                confidence=0.3,
                original_text=text,
                is_mixed_language=False,
            )

    async def translate(
        self,
        text: str,
        source_language: SupportedLanguage,
        target_language: SupportedLanguage,
        context: str | None = None,
    ) -> TranslationResult:
        """
        Translate text between supported languages

        Args:
            text: Text to translate
            source_language: Source language
            target_language: Target language
            context: Optional context for better translation

        Returns:
            TranslationResult with translated text
        """
        if source_language == target_language:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=source_language,
                target_language=target_language,
                confidence=1.0,
            )

        try:
            context_note = f"\nContext: {context}" if context else ""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=f"""You are a professional translator specializing in home renovation and construction terminology.
Translate from {source_language.name} to {target_language.name}.
Maintain the professional but friendly tone appropriate for a premium renovation company.
Preserve any company names, measurements, and technical terms accurately.
{context_note}

Return only the translated text, no explanations.""",
                messages=[{"role": "user", "content": f"Translate this text:\n\n{text}"}],
            )

            translated = response.content[0].text.strip()

            return TranslationResult(
                original_text=text,
                translated_text=translated,
                source_language=source_language,
                target_language=target_language,
                confidence=0.95,
            )

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return TranslationResult(
                original_text=text,
                translated_text=text,  # Return original on failure
                source_language=source_language,
                target_language=target_language,
                confidence=0.0,
            )

    async def translate_to_english(self, text: str) -> TranslationResult:
        """
        Detect language and translate to English

        Args:
            text: Text in any supported language

        Returns:
            TranslationResult with English translation
        """
        detection = await self.detect_language(text)

        if detection.detected_language == SupportedLanguage.ENGLISH:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=SupportedLanguage.ENGLISH,
                target_language=SupportedLanguage.ENGLISH,
                confidence=detection.confidence,
            )

        return await self.translate(text, detection.detected_language, SupportedLanguage.ENGLISH)

    async def translate_response(
        self, response_text: str, user_language: SupportedLanguage
    ) -> TranslationResult:
        """
        Translate AI response to user's preferred language

        Args:
            response_text: Response in English
            user_language: User's preferred language

        Returns:
            TranslationResult with translated response
        """
        return await self.translate(
            response_text,
            SupportedLanguage.ENGLISH,
            user_language,
            context="Home renovation customer service conversation",
        )

    def get_greeting(self, language: SupportedLanguage) -> str:
        """Get localized greeting"""
        return self.GREETINGS.get(language, self.GREETINGS[SupportedLanguage.ENGLISH])

    def get_term_translation(self, term: str, target_language: SupportedLanguage) -> str:
        """Get translation for common renovation term"""
        term_lower = term.lower()
        if term_lower in self.RENOVATION_TERMS:
            translations = self.RENOVATION_TERMS[term_lower]
            return translations.get(target_language, term)
        return term

    async def set_user_preference(self, user_id: str, language: SupportedLanguage) -> None:
        """Set user's language preference"""
        if user_id in self._user_preferences:
            self._user_preferences[user_id].preferred_language = language
        else:
            self._user_preferences[user_id] = LanguagePreference(
                user_id=user_id, preferred_language=language
            )
        logger.info(f"Set language preference for {user_id}: {language.name}")

    async def get_user_preference(self, user_id: str) -> LanguagePreference | None:
        """Get user's language preference"""
        return self._user_preferences.get(user_id)

    async def auto_detect_and_set_preference(self, user_id: str, text: str) -> SupportedLanguage:
        """
        Auto-detect language from user input and set preference

        Args:
            user_id: User identifier
            text: User's message

        Returns:
            Detected/preferred language
        """
        detection = await self.detect_language(text)

        pref = self._user_preferences.get(user_id)

        if pref:
            # Add to detected languages
            if detection.detected_language not in pref.detected_languages:
                pref.detected_languages.append(detection.detected_language)

            # If detected with high confidence and different from preference, update
            if detection.confidence > 0.8:
                # Count how many times this language has been detected
                lang_count = pref.detected_languages.count(detection.detected_language)
                if lang_count >= 2:  # Consistent detection
                    pref.preferred_language = detection.detected_language
        else:
            # Create new preference
            self._user_preferences[user_id] = LanguagePreference(
                user_id=user_id,
                preferred_language=detection.detected_language,
                detected_languages=[detection.detected_language],
            )

        return self._user_preferences[user_id].preferred_language

    async def process_multilingual_message(self, user_id: str, message: str) -> dict:
        """
        Process a message handling language detection and translation

        Args:
            user_id: User identifier
            message: User's message

        Returns:
            Dict with original, translated, and detected language info
        """
        # Detect language
        detection = await self.detect_language(message)

        # Update preference
        user_lang = await self.auto_detect_and_set_preference(user_id, message)

        # Translate to English if needed
        english_text = message
        if detection.detected_language != SupportedLanguage.ENGLISH:
            translation = await self.translate_to_english(message)
            english_text = translation.translated_text

        return {
            "original_message": message,
            "english_message": english_text,
            "detected_language": detection.detected_language.value,
            "detected_language_name": detection.detected_language.name,
            "confidence": detection.confidence,
            "user_preferred_language": user_lang.value,
            "needs_translation": detection.detected_language != SupportedLanguage.ENGLISH,
        }

    async def prepare_response(self, user_id: str, english_response: str) -> dict:
        """
        Prepare response in user's preferred language

        Args:
            user_id: User identifier
            english_response: Response text in English

        Returns:
            Dict with response in user's language
        """
        pref = await self.get_user_preference(user_id)

        if not pref or pref.preferred_language == SupportedLanguage.ENGLISH:
            return {
                "response": english_response,
                "language": SupportedLanguage.ENGLISH.value,
                "was_translated": False,
            }

        translation = await self.translate_response(english_response, pref.preferred_language)

        return {
            "response": translation.translated_text,
            "original_response": english_response,
            "language": pref.preferred_language.value,
            "was_translated": True,
            "confidence": translation.confidence,
        }

    def get_language_support_message(self, language: SupportedLanguage) -> str:
        """Get message explaining language support"""
        messages = {
            SupportedLanguage.ENGLISH: "I can communicate with you in multiple languages including Polish, Spanish, French, Arabic, and Portuguese.",
            SupportedLanguage.POLISH: "Mogę komunikować się z Tobą po polsku. W czym mogę pomóc?",
            SupportedLanguage.SPANISH: "Puedo comunicarme contigo en español. ¿En qué puedo ayudarte?",
            SupportedLanguage.FRENCH: "Je peux communiquer avec vous en français. Comment puis-je vous aider?",
            SupportedLanguage.ARABIC: "يمكنني التواصل معك باللغة العربية. كيف يمكنني مساعدتك؟",
            SupportedLanguage.PORTUGUESE: "Posso comunicar consigo em português. Como posso ajudar?",
        }
        return messages.get(language, messages[SupportedLanguage.ENGLISH])


# Module-level instance
language_service = LanguageService()
