import os
import json
import re
from core.logger import log

# This class helps us show the bot in different languages (like Hungarian or English)
class LocalizationService:
    def __init__(self, default_lang="hu"):
        self.default_lang = default_lang
        self.current_lang = default_lang
        self.translations = {}
        # We load the default language when we start
        log.info(f"[DEBUG] LocalizationService: Initializing for {default_lang}")
        self.load_translations(default_lang)
        log.info(f"[DEBUG] LocalizationService: Initialization for {default_lang} complete.")

    def load_translations(self, lang):
        """This function loads the right language file (locales/hu.json or locales/en.json)."""
        self.current_lang = lang
        # Folders and file name setup
        locales_dir = "locales"
        file_name = f"{lang}.json"
        file_path = os.path.join(locales_dir, file_name)
        
        # Fallback for old structure if transition isn't complete (Optional but safe)
        if not os.path.exists(file_path):
            old_file_name = "messages.json" if lang == "hu" else f"messages_{lang}.json"
            if os.path.exists(old_file_name):
                file_path = old_file_name
        
        log.info(f"[Localization] Checking {file_path}...")
        if os.path.exists(file_path):
            log.info(f"[DEBUG] LocalizationService: {file_name} exists. Opening...")
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    log.info(f"[DEBUG] LocalizationService: {file_name} opened. Loading JSON...")
                    # We load the JSON data and update our dictionary
                    new_data = json.load(f)
                    log.info(f"[DEBUG] LocalizationService: JSON loaded from {file_name}.")
                    self.translations.clear()
                    self.translations.update(new_data)
                log.info(f"Loaded {len(self.translations)} translation keys for language: {lang}")
            except Exception as e:
                # If something goes wrong, we go back to Hungarian as a backup
                log.error(f"Failed to load translations for {lang}: {e}")
                if lang != "hu":
                    self.load_translations("hu") 
        else:
            # If the file is missing, we also use Hungarian as a backup
            log.warning(f"Translation file {file_name} not found. Falling back to default.")
            if lang != "hu":
                self.load_translations("hu")

    def get(self, key, default=None, **kwargs):
        """This function gets a translated text and fills in any variables/icons."""
        # 1. Look for the 'key' in our dictionary
        text = self.translations.get(key, default or key)
        
        if not isinstance(text, str):
            text = str(text)

        # 2. Support Icon placeholders like {SUCCESS} or {ERROR}
        if "{" in text:
            try:
                from core.icons import Icons
                placeholders = re.findall(r"\{([A-Z0-9_]+)\}", text)
                for p in placeholders:
                    if hasattr(Icons, p):
                        icon_val = getattr(Icons, p)
                        text = text.replace(f"{{{p}}}", str(icon_val))
            except Exception as e:
                log.error(f"[Localization] Icon replacement failed for '{key}': {e}")

        # 3. Support for dynamic variables (.format(**kwargs))
        try:
            return text.format(**kwargs)
        except Exception as e:
            # If we messed up the formatting, just return the plain text
            log.error(f"Error formatting translation key '{key}': {e}")
            return text

    def localize_commands(self, tree, guild=None):
        """This function translates only the descriptions of our slash commands."""
        try:
            commands = tree.get_commands(guild=guild)
            for cmd in commands:
                # We look for a description key like 'desc_status'
                key = f"desc_{cmd.name.replace('-', '_')}"
                if key in self.translations:
                    cmd.description = self.translations[key]
                
                # Note: Parameter descriptions are read-only in discord.py, 
                # so we skip them here or use a Translator class for those.
        except Exception as e:
            log.error(f"Error during command localization: {e}")
