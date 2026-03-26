import os
import json
from core.logger import log

# This class helps us show the bot in different languages (like Hungarian or English)
class LocalizationService:
    def __init__(self, default_lang="hu"):
        self.default_lang = default_lang
        self.current_lang = default_lang
        self.translations = {}
        # We load the default language when we start
        self.load_translations(default_lang)

    def load_translations(self, lang):
        """This function loads the right language file (messages.json or messages_en.json)."""
        self.current_lang = lang
        # Hungarian is special, it uses the main messages.json file
        file_name = "messages.json" if lang == "hu" else f"messages_{lang}.json"
        
        if os.path.exists(file_name):
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    # We load the JSON data and update our dictionary
                    new_data = json.load(f)
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
        """This function gets a translated text and fills in any variables."""
        # We look for the 'key' in our dictionary
        text = self.translations.get(key, default or key)
        try:
            # .format(**kwargs) replaces things like {name} with real values
            return str(text).format(**kwargs)
        except Exception as e:
            # If we messed up the formatting, just return the plain text
            log.error(f"Error formatting translation key '{key}': {e}")
            return str(text)

    def localize_commands(self, tree, guild=None):
        """This function translates the names and descriptions of our Discord commands."""
        try:
            # We get the commands for the specified guild (or global ones)
            commands = tree.get_commands(guild=guild)
            for cmd in commands:
                # 1. Translate Command Description
                # We look for a description key like 'desc_status'
                key = f"desc_{cmd.name.replace('-', '_')}"
                if key in self.translations:
                    cmd.description = self.translations[key]
                
                # 2. Translate Parameters
                # AppCommand objects have a 'parameters' attribute
                if hasattr(cmd, 'parameters'):
                    for param in cmd.parameters:
                        param_key = f"desc_param_{param.name.replace('-', '_')}"
                        if param_key in self.translations:
                            param.description = self.translations[param_key]
        except Exception as e:
            log.error(f"Error during command localization: {e}")
