"""Small desktop entry point; analysis runs outside the UI thread."""
import os,queue,threading,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from .cli import run_extract
from .profiles import get_profiles


def main():
    root=tk.Tk();root.title('Aislador de HAR');root.geometry('850x510');root.minsize(600,380)
    frame=ttk.Frame(root,padding=14);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Seleccioná los HAR. Se conservarán los originales y se aislarán protocolo y novedades.').pack(anchor='w')
    files=[];label=tk.StringVar(value='Ningún HAR seleccionado');out=tk.StringVar(value=str(Path.home()/'Documents'/'Aislador-salidas'))
    labels={'Automático':'auto',**{p['name']:p['key'] for p in get_profiles().values()}}
    provider=tk.StringVar(value='Automático');messages=queue.Queue()
    def choose():
        chosen=filedialog.askopenfilenames(title='HAR para analizar',filetypes=[('Capturas HAR','*.har'),('Todos','*.*')])
        if chosen:files[:]=chosen;label.set(str(len(files))+' captura(s) seleccionada(s)')
    row=ttk.Frame(frame);row.pack(fill='x',pady=12)
    ttk.Button(row,text='Elegir HAR…',command=choose).pack(side='left');ttk.Label(row,textvariable=label).pack(side='left',padx=12)
    ttk.Label(frame,text='Proveedor (Auto intenta identificarlo por dominio y protocolo):').pack(anchor='w')
    ttk.Combobox(frame,textvariable=provider,values=list(labels),state='readonly').pack(fill='x',pady=4)
    ttk.Label(frame,text='Carpeta de resultados:').pack(anchor='w',pady=(10,0))
    row=ttk.Frame(frame);row.pack(fill='x')
    ttk.Entry(row,textvariable=out).pack(side='left',fill='x',expand=True)
    def destination():
        chosen=filedialog.askdirectory(title='Guardar resultados en')
        if chosen:out.set(chosen)
    ttk.Button(row,text='Elegir…',command=destination).pack(side='left',padx=(8,0))
    log=tk.Text(frame,height=11,wrap='word',state='disabled');log.pack(fill='both',expand=True,pady=12)
    def append(message):
        log.configure(state='normal');log.insert('end',message+'\n');log.see('end');log.configure(state='disabled')
    def worker(selected,key,target):
        try:
            results=run_extract(selected,key,Path(target),progress=lambda message:messages.put(('log',message)))
            for r in results:messages.put(('log','Resultado: '+r['output']))
            messages.put(('done',None))
        except Exception as exc:messages.put(('error',str(exc)))
    def start():
        if not files:messagebox.showinfo('Elegí capturas','Seleccioná al menos un archivo HAR.');return
        run.configure(state='disabled');append('Analizando…')
        threading.Thread(target=worker,args=(list(files),labels[provider.get()],out.get()),daemon=True).start()
    def poll():
        try:
            while True:
                kind,value=messages.get_nowait()
                if kind=='log':append(value)
                else:
                    run.configure(state='normal')
                    if kind=='error':append('Error: '+value)
                    else:append('Terminado. Abrí resumen.md dentro de cada carpeta de resultados.')
        except queue.Empty:pass
        root.after(120,poll)
    buttons=ttk.Frame(frame);buttons.pack(fill='x')
    run=ttk.Button(buttons,text='Analizar',command=start);run.pack(side='left')
    def open_folder():
        path=Path(out.get());path.mkdir(parents=True,exist_ok=True)
        if hasattr(os,'startfile'):os.startfile(str(path))
        else:messagebox.showinfo('Resultados',str(path))
    ttk.Button(buttons,text='Abrir resultados',command=open_folder).pack(side='left',padx=8)
    ttk.Button(buttons,text='Cerrar',command=root.destroy).pack(side='right')
    root.after(120,poll);root.mainloop()

if __name__=='__main__':main()
