import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PyPDF2 import PdfReader
import shutil
import time
import json
from pathlib import Path

try:
    import ttkbootstrap as tb
    from ttkbootstrap.constants import *
    TB_AVAILABLE = True
except Exception:
    TB_AVAILABLE = False

APP_TITLE = "WELCOME TO MY GUI! GREET FROM ROHIT "
# Soft limit to avoid OS errors — silently truncated if exceeded
SOFT_PATH_LIMIT = 4096  # very large, practical silent truncate

# Fixed credentials (per your request)
FIXED_USERNAME = "4696"
FIXED_PASSWORD = "4696"

# --------------------- Movable Calculator ---------------------
class MovableCalculator(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Calculator")
        self.geometry("220x260")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.configure(bg="#f0f0f0")

        self._drag_start_x = 0
        self._drag_start_y = 0

        header = tk.Frame(self, bg="#3a7bd5", height=28)
        header.pack(fill='x')
        header.bind("<Button-1>", self._start_move)
        header.bind("<B1-Motion>", self._on_move)

        tk.Label(header, text="Calc", bg="#3a7bd5", fg="white").pack(side='left', padx=8)
        tk.Button(header, text='✕', bg="#3a7bd5", fg='white', bd=0, command=self.destroy).pack(side='right', padx=6)

        self.display = tk.Entry(self, font=("Segoe UI", 14), justify='right')
        self.display.pack(fill='x', padx=8, pady=(8,4))

        btns = [
            ('7','8','9','/'),
            ('4','5','6','*'),
            ('1','2','3','-'),
            ('0','.','=','+'),
            ('C',)
        ]
        for row in btns:
            fr = tk.Frame(self, bg="#f0f0f0")
            fr.pack(fill='x', padx=8, pady=2)
            for val in row:
                b = tk.Button(fr, text=val, width=4, height=1, command=lambda v=val: self._on_btn(v))
                b.pack(side='left', padx=4)

    def _start_move(self, e):
        self._drag_start_x = e.x
        self._drag_start_y = e.y

    def _on_move(self, e):
        x = self.winfo_x() + e.x - self._drag_start_x
        y = self.winfo_y() + e.y - self._drag_start_y
        self.geometry(f"+{x}+{y}")

    def _on_btn(self, v):
        if v == '=':
            try:
                res = eval(self.display.get())
                self.display.delete(0, 'end')
                self.display.insert(0, str(res))
            except Exception:
                self.display.delete(0, 'end')
                self.display.insert(0, 'ERR')
        elif v == 'C':
            self.display.delete(0, 'end')
        else:
            self.display.insert('end', v)

# --------------------- Main PDF Dashboard ---------------------
class PDFDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.queue = queue.Queue()
        self.copy_thread = None
        self.check_thread = None
        self.cancel_check = False
        self.active_panel = None
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="Ready")

        # config file for "remember me"
        self.config_path = os.path.join(os.path.dirname(__file__), "app_config.json")
        self._load_config()

        self._build_ui()
        self.root.after(200, self._poll_queue)

        # Build and show login overlay (sliding)
        self._build_login_overlay()
        self._show_login_overlay()

    # ---------------- Config -----------------
    def _load_config(self):
        self.config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path,'r',encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = {}
        if 'last_user' not in self.config:
            self.config['last_user'] = ''

    def _save_config(self):
        try:
            with open(self.config_path,'w',encoding='utf-8') as f:
                json.dump(self.config, f)
        except:
            pass

    # ---------------- Build UI ---------------------
    def _build_ui(self):
        # Top blue border
        top_bar = tk.Frame(self.root, height=6, bg="#1E90FF")
        top_bar.pack(fill='x', side='top')

        # main horizontal layout: sidebar + content
        container = tk.Frame(self.root)
        container.pack(fill='both', expand=True)

        # Sidebar - grey
        sidebar_width = 220
        self.sidebar = tk.Frame(container, width=sidebar_width, bg="#d9d9d9", bd=1, relief='solid')
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="PDF Tools", font=("Segoe UI", 14, "bold"), bg="#d9d9d9").pack(pady=(12,8))

        self.btn_copy = ttk.Button(self.sidebar, text="📄 spit and rename", command=self.show_copy_ui)
        self.btn_copy.pack(fill='x', padx=12, pady=8)
        self.btn_check = ttk.Button(self.sidebar, text="✅ PDF Check", command=self.show_check_ui)
        self.btn_check.pack(fill='x', padx=12, pady=8)
        self.btn_home = ttk.Button(self.sidebar, text="🏠 Home", command=self.reset_all)
        self.btn_home.pack(fill='x', padx=12, pady=8)

        ttk.Separator(self.sidebar, orient='horizontal').pack(fill='x', pady=12)
        tk.Label(self.sidebar, text="Developed by Rohit", font=("Segoe UI", 9), bg="#d9d9d9").pack(side='bottom', pady=18)

        # Content area
        self.content = tk.Frame(container, bg="white")
        self.content.pack(side='left', fill='both', expand=True)

        self.home_frame = tk.Frame(self.content, bg='white')
        self.copy_frame = tk.Frame(self.content, bg='white')
        self.check_frame = tk.Frame(self.content, bg='white')

        self._build_home(self.home_frame)
        self._build_copy_ui(self.copy_frame)
        self._build_check_ui(self.check_frame)

        for f in (self.home_frame, self.copy_frame, self.check_frame):
            f.place(relx=1.0, rely=0, relwidth=1.0, relheight=1.0)

        status_bar = tk.Frame(self.content, bg='#f5f5f5')
        status_bar.pack(side='bottom', fill='x')
        ttk.Progressbar(status_bar, variable=self.progress_var, maximum=100).pack(fill='x', side='left', expand=True, padx=6, pady=6)
        tk.Label(status_bar, textvariable=self.status_var, bg='#f5f5f5').pack(side='right', padx=8)

    # ---------------- Home ---------------------
    def _build_home(self, parent):
        canvas = tk.Canvas(parent, bg='white')
        canvas.pack(fill='both', expand=True)

        def draw_scene():
            canvas.delete('all')
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            desk_h = int(h*0.35)
            canvas.create_rectangle(0,h-desk_h,w,h,fill='#f0e6d6',outline='')
            canvas.create_rectangle(50,h-desk_h-40,w-50,h-desk_h+20,fill='#8b5a2b',outline='')
            mx,my = 140,h-desk_h-150
            canvas.create_rectangle(mx,my,mx+180,my+110,fill='#222222')
            canvas.create_rectangle(mx+70,my+110,mx+110,my+120,fill='#444444')
            canvas.create_rectangle(mx+20,my+120,mx+160,my+140,fill='#cccccc')
            cx,cy=w-220,h-desk_h-30
            canvas.create_oval(cx-30,cy-80,cx+30,cy-20,fill='#ffd1dc',outline='')
            canvas.create_rectangle(cx-40,cy-20,cx+40,cy+30,fill='#444444',outline='')
            canvas.create_rectangle(260,my+20,320,my+60,fill='white',tags='paper')
        draw_scene()

        def animate():
            try:
                canvas.move('paper',2,0)
            except:
                pass
            parent.after(200,animate)
        parent.after(300, animate)
        tk.Label(parent, text=APP_TITLE, font=("Segoe UI",18,'bold'), bg='white').place(relx=0.5,rely=0.08,anchor='n')

    # ---------------- Copy UI ---------------------
    def _build_copy_ui(self, parent):
        tk.Label(parent,text=" SPLIT & RENAME PANNEL ",font=("Segoe UI",14,"bold"),bg='white').pack(anchor='w',pady=(8,6),padx=8)
        row_src = tk.Frame(parent,bg='white'); row_src.pack(fill='x',pady=4,padx=8)
        tk.Label(row_src,text="Source Folder:",bg='white').pack(side='left')
        self.copy_src_var = tk.StringVar()
        ttk.Entry(row_src,textvariable=self.copy_src_var).pack(side='left',fill='x',expand=True,padx=6)
        ttk.Button(row_src,text="Browse",command=self.browse_copy_folder).pack(side='left')

        row_total = tk.Frame(parent,bg='white'); row_total.pack(fill='x',pady=4,padx=8)
        tk.Label(row_total,text="Total PDFs in Source:",bg='white').pack(side='left')
        self.total_label=tk.Label(row_total,text="0",bg='white',font=("Segoe UI",10,'bold'))
        self.total_label.pack(side='left',padx=6)
        ttk.Button(row_total,text="Refresh",command=self._refresh_total).pack(side='left',padx=6)

        row_main = tk.Frame(parent,bg='white'); row_main.pack(fill='x',pady=4,padx=8)
        tk.Label(row_main,text="Main Folder:",bg='white').pack(side='left')
        self.copy_main_var = tk.StringVar()
        ttk.Entry(row_main,textvariable=self.copy_main_var).pack(side='left',fill='x',expand=True,padx=6)

        row_sub = tk.Frame(parent,bg='white'); row_sub.pack(fill='x',pady=4,padx=8)
        tk.Label(row_sub,text="Subfolder:",bg='white').pack(side='left')
        self.copy_sub_var = tk.StringVar()
        self.copy_sub_entry = ttk.Entry(row_sub,textvariable=self.copy_sub_var)
        self.copy_sub_entry.pack(side='left',fill='x',expand=True,padx=6)
        # no popup on long names
        self.copy_sub_var.trace_add('write',lambda *a: None)

        self.start_page_var=tk.StringVar(value='1')
        self.end_page_var=tk.StringVar()
        row_range=tk.Frame(parent,bg='white'); row_range.pack(fill='x',pady=4,padx=8)
        tk.Label(row_range,text="Start Page:",bg='white').pack(side='left')
        ttk.Entry(row_range,textvariable=self.start_page_var,width=6).pack(side='left',padx=6)
        tk.Label(row_range,text="End Page:",bg='white').pack(side='left')
        e_end=ttk.Entry(row_range,textvariable=self.end_page_var,width=6)
        e_end.pack(side='left',padx=6)
        e_end.bind('<Return>',lambda ev:self.start_copy())

        row_btn=tk.Frame(parent,bg='white'); row_btn.pack(fill='x',pady=8,padx=8)
        ttk.Button(row_btn,text=" SAVE ",command=self.start_copy).pack(side='left')
        ttk.Button(row_btn,text="Calculator",command=self._open_calc).pack(side='left',padx=6)

        self.copy_progress = ttk.Progressbar(parent,variable=self.progress_var,maximum=100)
        self.copy_progress.pack(fill='x',padx=8,pady=6)
        tk.Label(parent,textvariable=self.status_var,bg='white').pack(anchor='w',padx=8)

    # ---------------- Copy Functions ---------------------
    def _refresh_total(self):
        src=self.copy_src_var.get()
        if os.path.isdir(src):
            files=sorted([f for f in os.listdir(src) if f.lower().endswith('.pdf')])
            self.total_label.config(text=str(len(files)))
        else:
            self.total_label.config(text='0')

    def _open_calc(self):
        calc=MovableCalculator(self.root)
        x=self.root.winfo_x()+600
        y=self.root.winfo_y()+300
        try: calc.geometry(f"+{x}+{y}")
        except: pass

    # ---------------- Check UI ---------------------
    def _build_check_ui(self,parent):
        tk.Label(parent,text="PDF Open Checker",font=("Segoe UI",14,'bold'),bg='white').pack(anchor='w',pady=(8,6),padx=8)
        row_chk=tk.Frame(parent,bg='white'); row_chk.pack(fill='x',pady=4,padx=8)
        tk.Label(row_chk,text="Folder to Check:",bg='white').pack(side='left')
        self.check_folder_var=tk.StringVar()
        ttk.Entry(row_chk,textvariable=self.check_folder_var).pack(side='left',fill='x',expand=True,padx=6)
        ttk.Button(row_chk,text="Browse",command=self.browse_check_folder).pack(side='left')
        ttk.Button(parent,text="Check PDFs",command=self.start_check).pack(pady=8,padx=8)
        ttk.Button(parent,text="Cancel Check",command=self._cancel_check).pack(pady=4,padx=8)
        list_frame=tk.Frame(parent,bg='white'); list_frame.pack(fill='both',expand=True,padx=8,pady=6)
        self.check_listbox=tk.Listbox(list_frame)
        self.check_listbox.pack(fill='both',expand=True)
        self.check_listbox.bind('<Double-Button-1>',self._open_failed_file)
        self.check_progress=ttk.Progressbar(parent,maximum=100)
        self.check_progress.pack(fill='x',padx=8,pady=(0,8))

    # ---------------- Panel switch ---------------------
    def show_home(self,animated=False):
        self._activate_button(self.btn_home)
        self._show_panel(self.home_frame,animated=animated)

    def show_copy_ui(self):
        self._activate_button(self.btn_copy)
        self._show_panel(self.copy_frame,animated=True)

    def show_check_ui(self):
        self._activate_button(self.btn_check)
        self._show_panel(self.check_frame,animated=True)

    def _activate_button(self,btn):
        for b in (self.btn_copy,self.btn_check,self.btn_home):
            try: b.state(['!pressed'])
            except: pass
        try: btn.state(['pressed'])
        except: pass

    def _show_panel(self,panel,animated=True):
        if self.active_panel==panel: return
        self.active_panel=panel
        panel.lift()
        if not animated:
            panel.place(relx=0,rely=0,relwidth=1.0,relheight=1.0)
            return
        steps=18
        start=1.0
        def step(i):
            relx=start-(i/steps)
            panel.place(relx=relx,rely=0,relwidth=1.0,relheight=1.0)
            if i<steps: panel.after(int(220/steps),lambda: step(i+1))
            else: panel.place(relx=0,rely=0,relwidth=1.0,relheight=1.0)
        step(0)

    # ---------------- Folder Browsers ---------------------
    def browse_copy_folder(self):
        folder=filedialog.askdirectory(title="Select Source Folder")
        if folder:
            self.copy_src_var.set(folder)
            self._refresh_total()

    def browse_check_folder(self):
        folder=filedialog.askdirectory(title="Select Folder to Check PDFs")
        if folder: self.check_folder_var.set(folder)

    # ---------------- Copy & Rename Logic ---------------------
    def start_copy(self):
        src=self.copy_src_var.get()
        main=self.copy_main_var.get().strip() or src
        sub=self.copy_sub_var.get().strip() or "split"
        try:
            start_page=int(self.start_page_var.get())
            end_page=int(self.end_page_var.get())
        except:
            messagebox.showwarning("Invalid Pages","Start/End pages must be integers.")
            return
        if not os.path.isdir(src):
            messagebox.showwarning("Invalid Folder","Source folder does not exist.")
            return
        files=sorted([f for f in os.listdir(src) if f.lower().endswith(".pdf")])
        total_files=len(files)
        if start_page<1 or end_page>total_files or start_page>end_page:
            messagebox.showwarning("Invalid Range",f"Enter valid page range: 1-{total_files}")
            return
        out_dir=os.path.join(main,sub)
        if os.path.exists(out_dir):
            messagebox.showerror("Folder Exists","Subfolder already exists. Change name to avoid overwrite.")
            return
        os.makedirs(out_dir,exist_ok=True)
        self.status_var.set("Copying & renaming PDFs...")
        self.progress_var.set(0)
        self.copy_thread=threading.Thread(target=self._copy_worker,args=(src,out_dir,files,start_page,end_page,sub),daemon=True)
        self.copy_thread.start()

    def _copy_worker(self,src,out_dir,files,start,end,sub):
        total=end-start+1
        for idx,i in enumerate(range(start-1,end)):
            src_file=os.path.join(src,files[i])
            dest_file=os.path.join(out_dir,f"{sub}_PAGE {idx+1}.pdf")
            # silently truncate if path extremely long (no popup)
            if len(dest_file) > SOFT_PATH_LIMIT:
                dest_file = dest_file[:SOFT_PATH_LIMIT-8] + ".pdf"
            try:
                shutil.copy2(src_file,dest_file)
            except Exception as e:
                self.queue.put(("error",f"Failed to copy {src_file}: {e}"))
                return
            pct=((idx+1)/total)*100
            self.queue.put(("progress",pct,f"Copied: {os.path.basename(dest_file)}"))
        self.queue.put(("copy_done",out_dir,end))

    # ---------------- PDF Check Logic ---------------------
    def start_check(self):
        folder=self.check_folder_var.get()
        if not os.path.isdir(folder):
            messagebox.showwarning("Invalid Folder","Select a valid folder.")
            return
        self.cancel_check=False
        self.status_var.set("Checking PDFs...")
        self.progress_var.set(0)
        self.check_listbox.delete(0,'end')
        self.check_thread=threading.Thread(target=self._check_worker,args=(folder,),daemon=True)
        self.check_thread.start()

    def _cancel_check(self):
        self.cancel_check=True
        self.status_var.set("Check canceled.")
        self.check_progress['value']=0

    def _check_worker(self,folder):
        pdfs=[]
        for root_dir,dirs,files in os.walk(folder):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(root_dir,f))
        total=len(pdfs)
        failed=[]
        for idx,pdf_file in enumerate(pdfs):
            if self.cancel_check: break
            try:
                reader=PdfReader(pdf_file)
                _=len(reader.pages)
                self.queue.put(("check_progress",((idx+1)/total)*100 if total else 0,pdf_file,True))
            except:
                failed.append(pdf_file)
                self.queue.put(("check_progress",((idx+1)/total)*100 if total else 0,pdf_file,False))
            time.sleep(0.01)
        self.queue.put(("check_done",failed))

    def _open_failed_file(self,event):
        sel=self.check_listbox.curselection()
        if not sel: return
        val=self.check_listbox.get(sel[0])
        if val.startswith("FAIL:"):
            file_name=val[6:]
            folder=self.check_folder_var.get()
            for root_dir,dirs,files in os.walk(folder):
                for f in files:
                    if f==file_name:
                        path=os.path.join(root_dir,f)
                        try:
                            if os.name=='nt': os.startfile(path)
                            else: import subprocess; subprocess.Popen(['xdg-open',path])
                        except: pass
                        return

    # ---------------- Queue Polling ---------------------
    def _poll_queue(self):
        try:
            while True:
                item=self.queue.get_nowait()
                tag=item[0]
                if tag=="progress":
                    _,pct,msg=item
                    self.progress_var.set(pct)
                    self.status_var.set(msg)
                elif tag=="error":
                    messagebox.showerror("Error",item[1])
                    self.status_var.set("Ready")
                elif tag=="copy_done":
                    outdir,last_end=item[1],item[2]
                    self.status_var.set("Copy completed")
                    self.progress_var.set(0)
                    try:
                        if os.name=='nt': os.startfile(outdir)
                        else: import subprocess; subprocess.Popen(['xdg-open',outdir])
                    except: pass
                    messagebox.showinfo("Success",f"Copy & Rename completed.\nOutput Folder: {outdir}")
                    # increment start page, clear end page, keep subfolder entry focus
                    try:
                        self.start_page_var.set(str(last_end+1))
                        self.end_page_var.set('')
                        self.copy_sub_entry.focus_set()
                    except: pass
                elif tag=="check_progress":
                    _,pct,pdf_file,ok=item
                    self.check_progress['value']=pct
                    if not ok:
                        self.check_listbox.insert('end',"FAIL:"+os.path.basename(pdf_file))
                elif tag=="check_done":
                    failed=item[1]
                    if not failed:
                        messagebox.showinfo("PDF Check","All PDFs opened successfully.")
                    self.status_var.set("Check complete")
                    self.check_progress['value']=0
        except queue.Empty:
            pass
        self.root.after(200,self._poll_queue)

    # ---------------- Reset / Home ---------------------
    def reset_all(self):
        self.copy_src_var.set('')
        self.copy_main_var.set('')
        self.copy_sub_var.set('')
        self.start_page_var.set('1')
        self.end_page_var.set('')
        self.check_folder_var.set('')
        self.check_listbox.delete(0,'end')
        self.progress_var.set(0)
        self.status_var.set('Ready')
        self.show_home(animated=True)

    # ---------------- Login Overlay ---------------------
    def _build_login_overlay(self):
        # overlay frame (start off-screen left)
        self.login_overlay = tk.Frame(self.root, bg='#000000')
        self.login_overlay.place(relx=-1.0, rely=0, relwidth=1.0, relheight=1.0)

        # background canvas - use solid dark background (no empty string)
        canvas = tk.Canvas(self.login_overlay, bg='#000000', highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        # central login card (white)
        card = tk.Frame(canvas, bg='#ffffff', bd=0, relief='ridge')
        card.place(relx=0.5, rely=0.5, anchor='center', width=420, height=300)

        tk.Label(card, text="Welcome — Please Sign In", font=("Segoe UI", 14, "bold"), bg='#ffffff').pack(pady=(16,6))

        form = tk.Frame(card, bg='#ffffff')
        form.pack(padx=18, pady=6, fill='x', expand=True)

        tk.Label(form, text="Username:", bg='#ffffff').pack(anchor='w')
        self.login_user_var = tk.StringVar(value=self.config.get('last_user',''))
        self.login_user_entry = ttk.Entry(form, textvariable=self.login_user_var)
        self.login_user_entry.pack(fill='x', pady=(0,8))

        tk.Label(form, text="Password:", bg='#ffffff').pack(anchor='w')
        self.login_pw_var = tk.StringVar()
        pw_row = tk.Frame(form, bg='#ffffff')
        pw_row.pack(fill='x', pady=(0,8))
        self.login_pw_entry = ttk.Entry(pw_row, textvariable=self.login_pw_var, show='*')
        self.login_pw_entry.pack(side='left', fill='x', expand=True)
        self._pw_shown = False
        self.pw_toggle_btn = ttk.Button(pw_row, text="Show", width=6, command=self._toggle_pw)
        self.pw_toggle_btn.pack(side='left', padx=(6,0))

        options_row = tk.Frame(form, bg='#ffffff')
        options_row.pack(fill='x', pady=(0,6))
        self.remember_var = tk.IntVar(value=1 if self.config.get('last_user') else 0)
        ttk.Checkbutton(options_row, text="Remember Me", variable=self.remember_var).pack(side='left')

        ttk.Button(options_row, text="Theme", command=self._toggle_login_theme).pack(side='right')

        btn_row = tk.Frame(card, bg='#ffffff')
        btn_row.pack(pady=(6,12))
        ttk.Button(btn_row, text="Login", command=self._perform_login).pack(side='left', padx=8)
        ttk.Button(btn_row, text="Forgot Password", command=self._info_forgot).pack(side='left', padx=8)

        # small footer
        tk.Label(card, text=f"(Use {FIXED_USERNAME} / {FIXED_PASSWORD})", bg='#ffffff', font=("Segoe UI",8)).pack(side='bottom', pady=(0,8))

        self.login_card = card
        self.login_canvas = canvas

    def _show_login_overlay(self):
        # sliding animation from left to center (relx -1 -> 0)
        steps = 18
        start = -1.0
        end = 0.0
        def step(i):
            relx = start + ((end - start) * (i/steps))
            self.login_overlay.place(relx=relx, rely=0, relwidth=1.0, relheight=1.0)
            if i < steps:
                self.root.after(int(300/steps), lambda: step(i+1))
            else:
                self.login_overlay.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                try:
                    self.login_user_entry.focus_set()
                except:
                    pass
        step(0)

    def _hide_login_overlay(self):
        # slide out to left and then remove
        steps = 12
        start = 0.0
        end = -1.0
        def step(i):
            relx = start + ((end - start) * (i/steps))
            self.login_overlay.place(relx=relx, rely=0, relwidth=1.0, relheight=1.0)
            if i < steps:
                self.root.after(int(220/steps), lambda: step(i+1))
            else:
                self.login_overlay.place_forget()
                # after successful login, show home
                self.show_home(animated=False)
        step(0)

    def _toggle_pw(self):
        if self._pw_shown:
            self.login_pw_entry.config(show='*')
            self.pw_toggle_btn.config(text='Show')
            self._pw_shown = False
        else:
            self.login_pw_entry.config(show='')
            self.pw_toggle_btn.config(text='Hide')
            self._pw_shown = True

    def _toggle_login_theme(self):
        # basic light/dark toggle for login card
        if getattr(self, 'theme_is_dark', False):
            # switch to light
            self.login_card.config(bg='#ffffff')
            for w in self.login_card.winfo_children():
                try: w.config(bg='#ffffff', fg='black')
                except: pass
            self.theme_is_dark = False
        else:
            self.login_card.config(bg='#222831')
            for w in self.login_card.winfo_children():
                try: w.config(bg='#222831', fg='white')
                except: pass
            self.theme_is_dark = True

    def _perform_login(self):
        username = self.login_user_var.get().strip()
        password = self.login_pw_var.get().strip()
        if not username or not password:
            messagebox.showwarning("Login", "Enter username and password.")
            return
        if username == FIXED_USERNAME and password == FIXED_PASSWORD:
            # success
            if self.remember_var.get():
                self.config['last_user'] = username
                self._save_config()
            else:
                self.config['last_user'] = ''
                self._save_config()
            self._hide_login_overlay()
        else:
            messagebox.showerror("Login Failed", "Incorrect username or password.")

    def _info_forgot(self):
        messagebox.showinfo("Forgot Password", f"This app uses fixed credentials.\nUsername: {FIXED_USERNAME}\nPassword: {FIXED_PASSWORD}")

# --------------------- Run App ---------------------
if __name__=="__main__":
    root=tk.Tk()
    root.geometry("980x620+200+100")
    app=PDFDashboard(root)
    root.mainloop()
 