ASC v0.4.6 RC3 - passive PV CSV import preview

IMPORTANT: experimental. The CSV model is independent from the existing active seasonal model.
CSV: Home Assistant history export sensor.solar_tageserzeugung, max 3 MB / 1100 days.
Panel requires entry_id in panel_custom configuration, e.g.:
  sidebar_title: ASC
  url_path: asc
  module_url: /asc_static/asc-panel.js?v=046rc3
  config:
    entry_id: <YOUR_ASC_CONFIG_ENTRY_ID>
Use the included panel_custom_v0.4.6_RC3.yaml with the existing entry_id.
Preview and confirmation are separate websocket calls. Existing imported dates never overwritten.
Active inverter and battery logic is unchanged. Passive seasonal weight stays 0% active.
Backup .storage before install; restore RC2 if errors.
