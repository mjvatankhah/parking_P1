"""Choose a local XLSX destination with explicit overwrite confirmation."""
from datetime import datetime
from pathlib import Path
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.components.common import RTLLabel, RoundedTextInput, PrimaryButton, SecondaryButton


class ExportDialog(Popup):
    def __init__(self,on_save,**kwargs):
        self.on_save=on_save
        self._overwrite=None
        root=BoxLayout(orientation='vertical',padding=16,spacing=10)
        home=Path.home()
        directory=home/'Downloads' if (home/'Downloads').is_dir() else home
        self.chooser=FileChooserListView(path=str(directory),dirselect=True)
        root.add_widget(self.chooser)
        self.filename=RoundedTextInput(text=f'traffic-report-{datetime.now():%Y%m%d-%H%M%S}.xlsx',
                                       size_hint_y=None,height=44,halign='left')
        root.add_widget(self.filename)
        self.error=RTLLabel(text='',size_hint_y=None,height=36,color=theme.rgba(theme.COLORS['offline']))
        root.add_widget(self.error)
        actions=BoxLayout(size_hint_y=None,height=44,spacing=10)
        cancel=SecondaryButton(text=theme.rtl('انصراف'))
        cancel.bind(on_release=lambda *_:self.dismiss())
        self.save=PrimaryButton(text=theme.rtl('ذخیره اکسل'))
        self.save.bind(on_release=self._save)
        actions.add_widget(cancel)
        actions.add_widget(self.save)
        root.add_widget(actions)
        super().__init__(title=theme.rtl('محل ذخیره خروجی اکسل'),title_font=theme.APP_FONT_NAME,
                         title_align='right',content=root,size_hint=(.8,.8),**kwargs)

    def _save(self,*_):
        name=self.filename.text.strip()
        if not name or '/' in name or '\\' in name or name in ('.','..'):
            self.error.set_text('نام فایل معتبر وارد کنید')
            return
        if not name.lower().endswith('.xlsx'):
            name+='.xlsx'
        target=Path(self.chooser.path)/name
        if target.exists() and self._overwrite!=target:
            self._overwrite=target
            self.save.text=theme.rtl('تأیید جایگزینی فایل')
            self.error.set_text('این فایل وجود دارد؛ برای جایگزینی دوباره تأیید کنید')
            return
        self.dismiss()
        self.on_save(target)
