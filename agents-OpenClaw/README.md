# Osekkai Python engine

このディレクトリのActive runtimeは「おっせかいおばさん」の判断・保存・契約検証です。

## Active

- `scripts/osekkai_*.py`
- `fixtures/osekkai/`
- `config/osekkai_policy.json`
- `tests/test_osekkai_*.py`
- `data/osekkai/`（実行時生成、Git追跡外）

Next.jsは`frontend/lib/server/osekkai-openclaw-bridge.ts`から、固定commandだけを`osekkai_cli.py`へ渡します。

## Reference only

prefixが`osekkai_`ではない一部scriptは、Calendar、Telegram、scheduler、Profile学習のP1参考用です。Active runtimeからはimportされていません。新機能は参考コードを直接共用せず、Osekkai専用moduleとして実装してください。

## Test

```powershell
python -m compileall scripts tests
python -m unittest discover -s tests -p "test_osekkai_*.py" -v
python scripts/osekkai_contracts.py --validate-all
```
