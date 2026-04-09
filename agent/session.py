"""
Gerencia o histórico de mensagens da sessão do agente.
"""


class Session:
    def __init__(self, max_history: int = 20):
        self.max_history  = max_history
        self.messages: list[dict] = []
        self.system_prompt: str   = ""

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_name: str, content: str):
        self.messages.append({
            "role":    "tool",
            "name":    tool_name,
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        """Retorna histórico completo com system prompt."""
        return [{"role": "system", "content": self.system_prompt}] + self.messages

    def _trim(self):
        """Mantém o histórico dentro do limite configurado."""
        if len(self.messages) > self.max_history:
            # Remove as mensagens mais antigas mas preserva o contexto imediato
            self.messages = self.messages[-self.max_history:]

    def clear(self):
        self.messages = []
