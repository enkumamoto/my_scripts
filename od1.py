import tkinter as tk
import numpy as np

def overdrive(input_signal, gain, tone, level):
    # Aplicar ganho
    output_signal = input_signal * gain

    # Aplicar equalização com filtro de tonalidade
    low = output_signal * np.maximum(0, output_signal) / (1 + tone)
    high = output_signal - low
    output_signal = low + high * tone

    # Ajustar o nível de saída
    output_signal *= level
    
    return output_signal

class OverdriveGUI(tk.Tk):
    def __init__(self, *args, **kwargs):
        tk.Tk.__init__(self, *args, **kwargs)

        self.title("Overdrive Plugin")
        self.geometry("400x200")

        self.gain = tk.DoubleVar()
        self.tone = tk.DoubleVar()
        self.level = tk.DoubleVar()

        gain_slider = tk.Scale(self, from_=0, to=2, resolution=0.1,
                               orient=tk.HORIZONTAL, variable=self.gain)
        gain_slider.pack()

        tone_slider = tk.Scale(self, from_=0, to=2, resolution=0.1,
                               orient=tk.HORIZONTAL, variable=self.tone)
        tone_slider.pack()

        level_slider = tk.Scale(self, from_=0, to=2, resolution=0.1,
                                orient=tk.HORIZONTAL, variable=self.level)
        level_slider.pack()

        apply_button = tk.Button(self, text="Apply",
                                 command=self.apply_overdrive)
        apply_button.pack()

    def apply_overdrive(self):
        input_signal = # Obtenha o sinal de entrada aqui
        output_signal = overdrive(input_signal, self. Gain.get(),
                                  self.tone.get(), self.level.get())
        # Aplique o sinal de saída aqui

if __name__ == "__main__":
    app = OverdriveGUI()
    app.mainloop()
