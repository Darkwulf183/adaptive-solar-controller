ASC v0.4.6 – battery safety and LOW-recovery release

INSTALLATION: Back up /config/.storage/adaptive_solar_controller.<entry_id> and the custom_components directory before updating. Replace custom_components/adaptive_solar_controller and restart Home Assistant.

Data migration: v0.4.4.5 Learning Transfer stored rebound_learning_reference in the existing HA Store. This release retains it, derives an interpolated provisional voltage-sag model, and removes the one-time importer and OneShot diagnostic. No capacity calibration is inferred from the provisional reference.

Modes: Gezielt uses FULL-gated controlled discharge and 10 descending steps with 120s load/480s relaxation; Automatisch passively records suitable load/relax transitions without forced power. A successful FULL from the current cycle is mandatory. The automatic mode may take multiple cycles and may record no successful run without useful transitions.

Hardware cutoff: number Battery hard cutoff voltage (20.0-25.0V; default 22.6V). The physical switch is only operated if the optional inverter_power_switch entity is configured; otherwise the 30W minimum command is NOT a true 0W disconnect. Configure and independently test hardware undervoltage protection. Monitor mode never actuates switches.

Capacity: stored_energy_kwh=0 represents an empty battery; usable_capacity_estimate_kwh is the distinct learned capacity. Capacity is not overwritten by zero on a failed cycle.

Fast grid control algorithm is preserved. Forecast trust, 72h weather planning and seasonal learning continue from the existing v0.4.4.5 code. Dual inverter failover remains reserved for v0.4.7.

This code has static checks and pure-function tests, not live HA or hardware validation. Start in Monitor and validate before enabling targeted calibration.
