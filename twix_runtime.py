from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from tg_settings import (BoolCodec, ChoiceCodec, DecimalCodec, DurationCodec, IntCodec, JsonCodec, Schema, Setting, Settings, SQLiteStore, StringCodec, TierCodec)
from tg_templates import AiogramTransport, Catalog, Renderer, SQLiteOverrides, UI, template_from_dict

ROOT=Path(__file__).resolve().parent
_runtime=None


def make_schema():
    definitions=json.loads((ROOT/'migration'/'setting_definitions.json').read_text())
    fields=[]
    for definition in definitions:
        d=dict(definition);kind=d.pop('type');default=d['default']
        if kind=='DecimalSetting':
            codec=DecimalCodec(Decimal(d['min_value']) if 'min_value' in d else None,Decimal(d['max_value']) if 'max_value' in d else None);default=Decimal(str(default))
        elif kind=='BoolSetting':codec=BoolCodec()
        elif kind=='IntSetting':codec=IntCodec(d.get('min_value'),d.get('max_value'))
        elif kind=='DurationSetting':codec=DurationCodec(d.get('min_seconds',0),d.get('max_seconds'))
        elif kind=='TierSetting':
            codec=TierCodec();default=[{k:Decimal(str(v)) for k,v in tier.items()} for tier in default]
        elif kind=='EnumSetting':codec=ChoiceCodec(d['options'])
        elif kind=='JsonSetting':codec=JsonCodec()
        elif kind=='StrSetting':codec=StringCodec(max_length=d.get('max_length'))
        else:raise ValueError(f'Unsupported legacy setting: {kind}')
        fields.append(Setting(d['key'],codec,default,d['title'],d.get('description',''),d.get('category','general')))
    fields.extend([
        Setting('payments.enabled',BoolCodec(),False,'Счета на оплату',category='payments'),
        Setting('payments.provider',ChoiceCodec(['cryptobot','xrocket']),'cryptobot','Провайдер',category='payments'),
        Setting('payments.currency',ChoiceCodec(['USDT','TON']),'USDT','Валюта счетов',category='payments'),
        Setting('payments.testnet',BoolCodec(),True,'CryptoPay testnet',category='payments'),
        Setting('payments.poll_interval',IntCodec(5,3600),15,'Проверка оплаты, секунд',category='payments'),
        Setting('payments.max_amount',DecimalCodec(Decimal('0.01')),Decimal('10000'),'Максимальный счет',category='payments'),
    ])
    return Schema(*fields)


class Runtime:
    def __init__(self,data_dir,*,legacy_settings=None,legacy_templates=None):
        directory=Path(data_dir);directory.mkdir(parents=True,exist_ok=True)
        self.schema=make_schema()
        self.settings_store=SQLiteStore(str(directory/'runtime.sqlite'))
        self.settings=Settings(self.schema,self.settings_store,scope='twix')
        self.template_store=SQLiteOverrides(str(directory/'runtime.sqlite'))
        self.catalog=Catalog(default_locale='ru',store=self.template_store)
        defaults=json.loads((ROOT/'migration'/'template_defaults.json').read_text())
        for key,variants in defaults.items():
            for locale,data in variants.items():
                self.catalog.register(key,data,locale=locale)
        self.bot=None
        self.ui=None
        try:
            self._migrate(directory,legacy_settings,legacy_templates)
            # Catalog.keys enumerates registered defaults, so re-register custom
            # legacy keys from durable overrides on EVERY process startup.
            for key,locale in self.template_store.db.execute('SELECT key,locale FROM template_overrides'):
                if key not in self.catalog.keys():self.catalog.register(key,{'text':''},locale=locale)
        except Exception:
            self.close()
            raise

    def _migrate(self,directory,settings_path,templates_path):
        marker=directory/'libraries-v1-migration.json'
        db=self.settings_store.db
        db.execute('CREATE TABLE IF NOT EXISTS runtime_migrations (name TEXT PRIMARY KEY,report TEXT NOT NULL)')
        db.commit()
        completed=db.execute('SELECT report FROM runtime_migrations WHERE name=?',('libraries-v1',)).fetchone()
        if completed:
            if not marker.exists():
                tmp=marker.with_suffix('.tmp');tmp.write_text(completed[0]);tmp.replace(marker)
            return
        if marker.exists():return  # Compatibility with pre-transactional marker.
        # Legacy files remain byte-for-byte untouched. Validate all input before
        # writing; failure aborts startup rather than silently replacing values.
        # Explicit migration sources must exist; a typo must not commit a
        # defaults-only completion marker that blocks later real migration.
        for source in (settings_path,templates_path):
            if source is not None and not Path(source).is_file():
                raise FileNotFoundError('Explicit legacy migration source is not a file')
        raw=json.loads(Path(settings_path).read_text()) if settings_path else {}
        unknown=sorted(set(raw)-{s.key for s in self.schema.fields()})
        if unknown:raise ValueError(f'Unknown legacy settings require explicit migration: {unknown}')
        encoded={}
        for key,value in raw.items():
            s=self.schema.get(key)
            # Legacy runtime.set stores JSON inside outer JSON strings.
            if isinstance(value,str):
                try:value=json.loads(value,parse_float=Decimal)
                except json.JSONDecodeError:pass
            if isinstance(s.codec,DecimalCodec):value=Decimal(str(value))
            elif isinstance(s.codec,TierCodec):value=[{k:Decimal(str(v)) for k,v in tier.items()} for tier in value]
            elif isinstance(s.codec,StringCodec) and not isinstance(value,str):value=str(value)
            encoded[key]=s.codec.encode(s.checked(value))
        raw_templates=json.loads(Path(templates_path).read_text()) if templates_path else {}
        patches=[]
        for storage_key,data in raw_templates.items():
            key,locale=storage_key.rsplit(':',1) if ':' in storage_key else (storage_key,'ru')
            # Existing customer overrides not present in defaults are retained.
            if key not in self.catalog.keys():self.catalog.register(key,{'text':''},locale=locale)
            base=asdict(self.catalog.get(key,locale))
            # Legacy storage may contain a partial patch: retain default buttons
            # and text, and let explicit legacy media fields override base media.
            merged={**base,**data}
            if 'media_type' in data or 'media_file_id' in data:merged.pop('media',None)
            candidate=template_from_dict(merged)
            patches.append((key,locale,asdict(candidate)))
        # Settings and template overrides share one SQLite file: commit them
        # together rather than partially applying a multi-template migration.
        db=self.settings_store.db
        db.execute('BEGIN IMMEDIATE')
        try:
            version,_=self.settings_store.snapshot('twix')
            if version==0 and encoded:
                db.execute('INSERT OR REPLACE INTO settings_scopes VALUES (?,?,?)',('twix',1,json.dumps(encoded,ensure_ascii=False,allow_nan=False)))
            for key,locale,patch in patches:
                db.execute('INSERT OR REPLACE INTO template_overrides VALUES (?,?,?)',(key,locale,json.dumps(patch,ensure_ascii=False,allow_nan=False)))
            report=json.dumps({'version':1,'settings':len(encoded),'templates':len(patches),'sources_read_only':True},indent=2)
            db.execute('INSERT INTO runtime_migrations VALUES (?,?)',('libraries-v1',report))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        tmp=marker.with_suffix('.tmp')
        tmp.write_text(report)
        tmp.replace(marker)

    def attach_bot(self,bot):
        self.bot=bot
        self.ui=UI(AiogramTransport(bot),self.catalog,Renderer())
        return self.ui

    def close(self):
        self.settings_store.close();self.template_store.close()


def configure(*,data_dir=None,legacy_settings=None,legacy_templates=None):
    global _runtime
    if _runtime is not None:_runtime.close()
    _runtime=None
    if data_dir is None:
        from config import DATA_DIR,SETTINGS_FILE,TEMPLATES_FILE
        data_dir=DATA_DIR
        legacy_settings=SETTINGS_FILE if Path(SETTINGS_FILE).is_file() else None
        legacy_templates=TEMPLATES_FILE if Path(TEMPLATES_FILE).is_file() else None
    _runtime=Runtime(data_dir,legacy_settings=legacy_settings,legacy_templates=legacy_templates)
    return _runtime


def runtime():
    if _runtime is None:raise RuntimeError('Call twix_runtime.configure() before accessing settings/UI')
    return _runtime
