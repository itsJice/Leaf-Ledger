# Schedules

The following scheduled jobs were configured in Riff. You'll need to recreate these using cron or a similar scheduler.

## Weekly Price Sync — All Suppliers
- **Cron:** `{'type': 'cron', 'timezone': 'Etc/UTC', 'cronExpression': '0 2 * * 1'}`
- **Endpoint:** `/sync-prices-bulk`
- **Status:** Enabled

## How to Set Up

You can recreate these schedules using:
- **cron** (Linux/macOS): Add entries to crontab
- **systemd timers** (Linux): Create timer units
- **GitHub Actions** (CI/CD): Use schedule triggers
- **Cloud providers**: Use cloud scheduler services

### Example cron setup:

```bash
# Edit crontab
crontab -e

# Add entries for each schedule
# Format: minute hour day month weekday command
0 9 * * * curl -X POST http://localhost:8000/api/your-endpoint
```
