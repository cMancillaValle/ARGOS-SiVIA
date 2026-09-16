# logic/decision_engine.py

import time

class DecisionEngine:
    def __init__(self):
        self.ultimo_acceso = 0
        self.cooldown = 3  # segundos
        self.estado_anterior = None

    def evaluar(self, estado):
        ahora = time.time()

        condicion_acceso = (
            estado["persona"] and
            estado["brazo"] and
            estado["mano"] == "abierta" and
            estado["tarjeta"]
        )

        # Detectar cambio de estado (edge detection)
        if condicion_acceso:
            if ahora - self.ultimo_acceso > self.cooldown:
                self.ultimo_acceso = ahora
                return "acceso"

        return None