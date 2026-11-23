# Rock 5T: clocks locked at maximum

By default the Rock 5T (RK3588) lowers its CPU, memory, NPU and GPU clocks when idle and raises them under load. Locking them at maximum makes LLM inference a little faster, because the memory clock no longer has to ramp up at the start of each answer.

**Measured on qwen3.5:4b** (CPU, llama.cpp, same model file and command):

| | Default clocks | Locked at maximum | Change |
|---|---:|---:|---:|
| Prompt processing | 12.1 tokens/s | 13.5 tokens/s | +12% |
| Generation | 4.37 tokens/s | 4.65 tokens/s | +6% |

The cost is slightly more heat and power at idle. With the fan, temperatures stay well below the 85 °C throttle point.

## What it sets

| Part | Default | Locked |
|---|---|---|
| CPU (all clusters) | `ondemand` governor | `performance` governor (1.8 GHz little, 2.3 GHz big cores) |
| Memory (`dmc`) | 534–2400 MHz | 2400 MHz |
| NPU (`fdab0000.npu`) | 300–1000 MHz | 1000 MHz |
| GPU (`fb000000.gpu`) | 300–1000 MHz | 1000 MHz |

The memory, NPU and GPU have no `performance` governor on this kernel, so they are locked by raising their minimum clock to their maximum.

## Install (keeps the settings after a reboot)

From the repository root:

```bash
sudo install -m 755 hardware/processing_unit/rock5t/rock5t-max-clocks.sh /usr/local/sbin/
sudo install -m 644 hardware/processing_unit/rock5t/rock5t-max-clocks.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rock5t-max-clocks.service
```

Check it:

```bash
systemctl status rock5t-max-clocks.service --no-pager
sudo /usr/local/sbin/rock5t-max-clocks.sh status
```

## Turn it off

```bash
sudo systemctl disable --now rock5t-max-clocks.service   # stops it and puts the defaults back
```

To use it once without installing: `sudo hardware/processing_unit/rock5t/rock5t-max-clocks.sh apply` (resets on reboot), and `... reset` to undo.
