"""Plate registration grouped into allowed, guest and blocked categories."""
from threading import Thread
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from reno.ui import theme
from reno.ui.components.common import Card,RTLLabel,PrimaryButton,SecondaryButton,styled_spinner
from reno.ui.components.plate_input import PlateSearchInput, format_plate
from reno.ui.components.page_shell import PageShell
from reno.ui.components.iranian_plate import PlainPlate
from reno.services.plate_registry_service import plate_registry_service

_LABELS={'allowed':'مجاز','guest':'میهمان','blocked':'غیرمجاز'}


class PlateRegistrationScreen(Screen):
    def __init__(self,on_navigate=None,**kwargs):
        super().__init__(**kwargs)
        self.category='allowed'
        self.offset=0
        self.total=0
        self._busy=False
        self._generation=0
        content=BoxLayout(orientation='vertical',spacing=16)
        form=Card(orientation='vertical',size_hint_y=None,height=150,padding=16,spacing=10,hover_effect=False)
        form.add_widget(RTLLabel(text='ثبت پلاک مجاز یا افزودن به بلک‌لیست',size_hint_y=None,height=28))
        controls=BoxLayout(size_hint_y=None,height=44,spacing=12)
        self.save=PrimaryButton(text=theme.rtl('ثبت پلاک'),size_hint_x=None,width=140)
        self.save.bind(on_release=lambda *_:self._save())
        controls.add_widget(self.save)
        self.permission=styled_spinner(values=[theme.rtl('مجاز'),theme.rtl('غیرمجاز')],initial=theme.rtl('مجاز'))
        self.permission.size_hint_x=None
        self.permission.width=150
        controls.add_widget(self.permission)
        self.plate=PlateSearchInput(hint_text=theme.rtl('مثلاً ۱۲ب۳۴۵۶۷'))
        controls.add_widget(self.plate)
        form.add_widget(controls)
        form.add_widget(RTLLabel(text='پلاک ثبت‌نشده میهمان است؛ تغییر دسته‌بندی، وضعیت ترددهای گذشته را تغییر نمی‌دهد.',font_size=12))
        content.add_widget(form)
        tabs=BoxLayout(size_hint_y=None,height=42,spacing=10)
        self.tabs={}
        for key,title in _LABELS.items():
            tab=SecondaryButton(text=theme.rtl(title))
            tab.bind(on_release=lambda _,k=key:self._select(k))
            self.tabs[key]=tab
            tabs.add_widget(tab)
        content.add_widget(tabs)
        table=Card(orientation='vertical',padding=16,spacing=10,hover_effect=False)
        self.message=RTLLabel(text='',size_hint_y=None,height=34,font_size=12)
        table.add_widget(self.message)
        self.holder=BoxLayout(orientation='vertical')
        table.add_widget(self.holder)
        footer=BoxLayout(size_hint_y=None,height=38,spacing=12)
        self.previous=SecondaryButton(text=theme.rtl('صفحه قبل'),size_hint_x=None,width=110)
        self.previous.bind(on_release=lambda *_:self._turn(-1))
        self.next=SecondaryButton(text=theme.rtl('صفحه بعد'),size_hint_x=None,width=110)
        self.next.bind(on_release=lambda *_:self._turn(1))
        self.page_label=RTLLabel(text='',halign='center',font_size=12)
        for item in (self.previous,self.page_label,self.next):
            footer.add_widget(item)
        table.add_widget(footer)
        content.add_widget(table)
        self.add_widget(PageShell('ثبت پلاک','plate_registration',content,on_navigate,subtitle='مدیریت پلاک‌های مجاز، میهمان و غیرمجاز'))
        self._controls()

    def _controls(self):
        self.save.disabled=self._busy
        self.plate.disabled=self.permission.disabled=self._busy
        self.holder.disabled=self._busy
        for key,tab in self.tabs.items():
            tab.disabled=self._busy
            tab.bg_color_normal=theme.rgba(theme.COLORS['primary_light' if key==self.category else 'surface'])
            tab._redraw()
        self.previous.disabled=self._busy or self.offset==0
        self.next.disabled=self._busy or self.offset+20>=self.total
        self.page_label.set_text(f'صفحه {theme.fa_number(self.offset//20+1)} · {theme.fa_number(self.total)} پلاک')

    def on_enter(self,*_):
        self._load()

    def on_leave(self,*_):
        self._generation+=1
        self._busy=False
        self._controls()

    def _select(self,key):
        if self._busy:
            return
        self.category=key
        self.offset=0
        self._load()

    def _turn(self,direction):
        offset=self.offset+direction*20
        if self._busy or offset<0 or offset>=self.total:
            return
        self.offset=offset
        self._load()

    def _load(self):
        if self._busy:
            return
        self._busy=True
        generation=self._generation
        category,offset=self.category,self.offset
        self._controls()
        def work():
            try:
                page,error=plate_registry_service.page(category,offset),''
            except Exception:
                page,error=None,'دریافت پلاک‌ها ناموفق بود؛ اتصال دیتابیس را بررسی کنید'
            Clock.schedule_once(lambda _:self._loaded(generation,page,error))
        Thread(target=work,daemon=True).start()

    def _loaded(self,generation,page,error):
        if generation!=self._generation:
            return
        self._busy=False
        self.holder.clear_widgets()
        if error:
            self.message.set_text(error)
        else:
            self.total,self.offset=page.total,page.offset
            self.message.set_text(f'پلاک‌های {_LABELS[self.category]}')
            scroll=ScrollView(do_scroll_x=False)
            rows=GridLayout(cols=1,size_hint_y=None,spacing=6)
            rows.bind(minimum_height=rows.setter('height'))
            for plate in page.plates:
                row=Card(size_hint_y=None,height=50,padding=[8,6],spacing=12,hover_effect=False)
                edit=SecondaryButton(text=theme.rtl('ویرایش'),size_hint_x=None,width=85)
                edit.bind(on_release=lambda _,p=plate:self._edit(p))
                row.add_widget(edit)
                if self.category!='guest':
                    remove=SecondaryButton(text=theme.rtl('میهمان کردن'),size_hint_x=None,width=110)
                    remove.bind(on_release=lambda _,p=plate:self._save(p,'guest'))
                    row.add_widget(remove)
                row.add_widget(RTLLabel(text=_LABELS[self.category],font_size=12,halign='center'))
                row.add_widget(PlainPlate(plate))
                rows.add_widget(row)
            if not page.plates:
                rows.add_widget(RTLLabel(text='پلاکی در این دسته وجود ندارد',size_hint_y=None,height=44,halign='center'))
            scroll.add_widget(rows)
            self.holder.add_widget(scroll)
        self._controls()

    def _edit(self,plate):
        self.plate.text=format_plate(plate) or plate
        self.permission.text=theme.rtl('غیرمجاز' if self.category=='blocked' else 'مجاز')

    def _save(self,plate=None,permission=None):
        if self._busy:
            return
        plate=plate if plate is not None else self.plate.text
        permission=permission or ('blocked' if self.permission.text==theme.rtl('غیرمجاز') else 'allowed')
        generation=self._generation
        self._busy=True
        self._controls()
        def work():
            try:
                plate_registry_service.save(plate,permission)
                error=''
            except ValueError as exc:
                error=str(exc)
            except Exception:
                error='ثبت پلاک ناموفق بود؛ اتصال دیتابیس را بررسی کنید'
            Clock.schedule_once(lambda _:self._saved(generation,permission,error))
        Thread(target=work,daemon=True).start()

    def _saved(self,generation,permission,error):
        if generation!=self._generation:
            return
        self._busy=False
        self._controls()
        if error:
            self.message.set_text(error)
            return
        self.plate.text=''
        self.category=permission
        self.offset=0
        self._load()
