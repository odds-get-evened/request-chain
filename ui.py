import tkinter as tk


class RequestChainWin(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Request Chain v0.0.1")
        self.geometry("800x600")
        self.center_win()

    def center_win(self):
        self.update_idletasks()
        w = 800
        h = 600
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w // 2) - (w // 2)
        y = (screen_h // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")


def main():
    app = RequestChainWin()
    app.mainloop()


if __name__ == "__main__":
    main()
