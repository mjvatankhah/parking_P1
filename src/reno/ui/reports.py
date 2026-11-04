"""Filtered traffic reports with bounded tables and asynchronous XLSX export."""
from threading import Thread
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.components.common import Card, RTLLabel, RoundedTextInput, PrimaryButton, SecondaryButton, styled_spinner
from reno.ui.components.page_shell import PageShell
from reno.ui.components.traffic_record import TrafficRecordRow, detection_header
from reno.ui.components.jalali_date_picker import JalaliDatePicker
from reno.ui.components.export_dialog import ExportDialog
from reno.services.report_service import ReportFilter, report_service

_COUNTS={theme.rtl('۲۰ تردد'):20,theme.rtl('۳۰ تردد'):30,theme.rtl('۵۰ تردد'):50,theme.rtl('همه ترددها'):None}


class ReportsScreen(Screen):
    def __init__(self,on_navigate=None,**kwargs):
        super().__init__(**kwargs)
        self._filters=ReportFilter()
        self._offset=0
        self._total=0
        self._busy=False
        self._exporting=False
        self._generation=0
        self._data_popup=None
        self._destination_dialog=None
        content=BoxLayout(orientation='vertical',spacing=16)
        action_style=dict(bg_color_normal=theme.rgba('#25898E'),bg_color_hover=theme.rgba('#309DA2'),
                          bg_color_down=theme.rgba('#1B6D72'),border_color=theme.rgba('#25898E'),
                          color=theme.rgba('#263238'))
        self.export_button=PrimaryButton(text=theme.rtl('خروجی اکسل'),size_hint=(None,None),
                                         size=(150,38),pos_hint={'center_y':.5},bold=False,**action_style)
        self.export_button.bind(on_release=self._choose_export)
        filters=Card(orientation='vertical',size_hint_y=None,height=114,padding=16,spacing=6,hover_effect=False)
        line=BoxLayout(spacing=12)
        self.apply_button=PrimaryButton(text=theme.rtl('اعمال فیلتر'),size_hint_x=None,width=130,
                                        size_hint_y=None,height=42,pos_hint={'center_y':.5},bold=False,**action_style)
        self.apply_button.bind(on_release=self._apply)
        line.add_widget(self.apply_button)
        self.end=JalaliDatePicker(size_hint_y=None,height=42,font_size=12)
        self.start=JalaliDatePicker(size_hint_y=None,height=42,font_size=12)
        self.plate=RoundedTextInput(hint_text=theme.rtl('مثلاً ۱۲ب۳۴۵۶۷'),size_hint_y=None,height=42)
        self.plate.bind(on_text_validate=self._apply)
        for title,widget in [('تا تاریخ',self.end),('از تاریخ',self.start),('جست‌وجوی پلاک مشخص',self.plate)]:
            field=BoxLayout(orientation='vertical',spacing=6)
            field.add_widget(RTLLabel(text=title,font_size=12,size_hint_y=None,height=22))
            field.add_widget(widget)
            line.add_widget(field)
        filters.add_widget(line)
        content.add_widget(filters)
        table=Card(orientation='vertical',padding=16,spacing=10,hover_effect=False)
        heading=BoxLayout(size_hint_y=None,height=40,spacing=12)
        self.count=styled_spinner(values=list(_COUNTS),initial=next(iter(_COUNTS)))
        self.count.size_hint_x=None
        self.count.width=160
        self.count.bind(text=self._count_changed)
        heading.add_widget(self.count)
        heading.add_widget(RTLLabel(text='ترددهای اخیر',font_size=18))
        table.add_widget(heading)
        self.status=RTLLabel(text='',size_hint_y=None,height=28,font_size=12)
        table.add_widget(self.status)
        self.table_holder=BoxLayout(orientation='vertical')
        table.add_widget(self.table_holder)
        self.footer=footer=BoxLayout(size_hint_y=None,height=38,spacing=12)
        self.previous=SecondaryButton(text=theme.rtl('صفحه قبل'),size_hint_x=None,width=110)
        self.previous.bind(on_release=lambda *_:self._turn(-1))
        self.next=SecondaryButton(text=theme.rtl('صفحه بعد'),size_hint_x=None,width=110)
        self.next.bind(on_release=lambda *_:self._turn(1))
        self.page_label=RTLLabel(text='',halign='center',font_size=12)
        for widget in (self.previous,self.page_label,self.next):
            footer.add_widget(widget)
        table.add_widget(footer)
        content.add_widget(table)
        self._shell=PageShell('گزارشات تردد','reports',content,on_navigate,
                              subtitle='جست‌وجو و خروجی گرفتن از سوابق تردد خودروها')
        self._shell.header.remove_widget(self._shell.header.ticket_button)
        self._shell.header.add_widget(self.export_button,index=len(self._shell.header.children))
        self.add_widget(self._shell)
        self._controls()

    @property
    def page_size(self):
        return _COUNTS[self.count.text] or 30

    def on_enter(self,*_):
        self._load()

    def on_leave(self,*_):
        self._generation+=1
        self._busy=False
        self._controls()
        if self._data_popup:
            self._data_popup.dismiss()
        if self._destination_dialog:
            self._destination_dialog.dismiss()

    def _controls(self):
        busy=self._busy or self._exporting
        self.apply_button.disabled=busy
        self.count.disabled=busy
        self.export_button.disabled=busy
        all_rows=_COUNTS[self.count.text] is None
        self.footer.height=38 if all_rows else 0
        self.footer.opacity=1 if all_rows else 0
        self.previous.disabled=busy or not all_rows or self._offset==0
        self.next.disabled=busy or not all_rows or self._offset+self.page_size>=self._total
        self.previous.opacity=self.next.opacity=1 if all_rows else 0
        self.page_label.set_text(f'صفحه {theme.fa_number(self._offset//30+1)} از {theme.fa_number(max(1,(self._total+29)//30))}' if all_rows else '')

    def _apply(self,*_):
        if self._busy or self._exporting:
            return
        try:
            filters=ReportFilter(self.plate.text.strip(),self.start.selected,self.end.selected)
        except ValueError as exc:
            self.status.set_text(str(exc))
            return
        self._filters=filters
        self._offset=0
        self._load()

    def _count_changed(self,*_):
        self._offset=0
        self._load()

    def _turn(self,direction):
        if self._busy or _COUNTS[self.count.text] is not None:
            return
        offset=self._offset+direction*30
        if offset<0 or offset>=self._total:
            return
        self._offset=offset
        self._load()

    def _load(self):
        if self._busy:
            return
        self._generation+=1
        generation=self._generation
        self._busy=True
        self.status.set_text('در حال دریافت ترددها…')
        self._controls()
        filters,limit,offset=self._filters,self.page_size,self._offset
        def work():
            try:
                result,error=report_service.page(filters,limit,offset),''
            except Exception:
                result,error=None,'دریافت گزارش ناموفق بود؛ اتصال پایگاه داده را بررسی و دوباره فیلتر را اعمال کنید'
            Clock.schedule_once(lambda _:self._loaded(generation,result,error))
        Thread(target=work,daemon=True).start()

    def _loaded(self,generation,result,error):
        if generation!=self._generation:
            return
        self._busy=False
        self.table_holder.clear_widgets()
        if error:
            self._total=0
            self.status.set_text(error)
            self.status.color=theme.rgba(theme.COLORS['offline'])
        else:
            self._total,self._offset=result.total,result.offset
            self.status.color=theme.rgba(theme.COLORS['text_secondary'])
            self.status.set_text(f'{theme.fa_number(len(result.records))} تردد از {theme.fa_number(result.total)} نتیجه')
            if not result.records:
                self.table_holder.add_widget(RTLLabel(text='ترددی با این فیلتر پیدا نشد',halign='center'))
            else:
                scroll=ScrollView(do_scroll_x=True,scroll_x=1,bar_width=4)
                rows=GridLayout(cols=1,size_hint=(None,None),spacing=4,width=760)
                rows.bind(minimum_height=rows.setter('height'))
                rows.add_widget(detection_header())
                scroll.bind(width=lambda w,v:setattr(rows,'width',max(760,v)))
                for record in result.records:
                    rows.add_widget(TrafficRecordRow(record))
                scroll.add_widget(rows)
                self.table_holder.add_widget(scroll)
        self._controls()

    def _choose_export(self,*_):
        if self._busy or self._exporting:
            return
        self._destination_dialog=ExportDialog(self._export)
        self._destination_dialog.open()

    def _export(self,path):
        if self._exporting:
            return
        self._exporting=True
        self.status.set_text('در حال ساخت خروجی اکسل از همه نتایج فیلترشده…')
        self._controls()
        filters=self._filters
        def work():
            try:
                count=report_service.export(filters,path)
                error=''
            except ValueError as exc:
                count,error=0,str(exc)
            except Exception:
                count,error=0,'ساخت فایل ناموفق بود؛ اتصال دیتابیس و دسترسی به پوشه را بررسی کنید'
            Clock.schedule_once(lambda _:self._exported(path,count,error))
        Thread(target=work,daemon=True).start()

    def _exported(self,path,count,error):
        self._exporting=False
        self._controls()
        message=error or f'{theme.fa_number(count)} تردد در فایل زیر ذخیره شد:\n{path}'
        self.status.set_text('خروجی اکسل ذخیره شد' if not error else error)
        if self.manager and self.manager.current!=self.name:
            return
        body=BoxLayout(orientation='vertical',padding=18,spacing=16)
        body.add_widget(RTLLabel(text=message,halign='center',font_size=13))
        okay=PrimaryButton(text=theme.rtl('باشه'),size_hint_y=None,height=42)
        body.add_widget(okay)
        popup=Popup(title=theme.rtl('خروجی اکسل'),title_font=theme.APP_FONT_NAME,content=body,
                    size_hint=(None,None),size=(520,260),auto_dismiss=False)
        self._data_popup=popup
        okay.bind(on_release=lambda *_:popup.dismiss())
        popup.open()
