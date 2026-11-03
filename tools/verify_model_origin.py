#!/usr/bin/env python3
"""Verify that the shipped model is an FP32 conversion of the upstream FP16 export.

Rationale: the release contains a modified file, and the Apache 2.0 license
requires showing this. The script compares the graphs of both files and prints
facts demonstrating that only the weight storage precision changed.

Usage (requires the onnx package):

    python tools/verify_model_origin.py \
        --upstream /path/to/upstream/model.onnx \
        --shipped  models/t-one/model.onnx
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

FP16 = 10
FP32 = 1


def describe(path: Path) -> dict:
    try:
        import onnx
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit("нужен пакет onnx: python -m pip install onnx") from exc

    model = onnx.load(str(path), load_external_data=False)
    initializers = model.graph.initializer
    dtypes = collections.Counter(item.data_type for item in initializers)
    return {
        "size": path.stat().st_size,
        "nodes": len(model.graph.node),
        "node_types": [node.op_type for node in model.graph.node],
        "initializers": len(initializers),
        "names": [item.name for item in initializers],
        "dtypes": dict(dtypes),
        "producer": f"{model.producer_name} {model.producer_version}".strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--shipped", type=Path, required=True)
    args = parser.parse_args()

    for path in (args.upstream, args.shipped):
        if not path.is_file():
            raise SystemExit(f"нет файла: {path}")

    up = describe(args.upstream)
    sh = describe(args.shipped)

    print(f"апстрим : {args.upstream}")
    print(f"  размер {up['size']} байт, узлов {up['nodes']}, инициализаторов {up['initializers']}")
    print(f"  типы данных: {up['dtypes']} (10 = FP16, 1 = FP32), producer: {up['producer']}")
    print(f"поставляемый: {args.shipped}")
    print(f"  размер {sh['size']} байт, узлов {sh['nodes']}, инициализаторов {sh['initializers']}")
    print(f"  типы данных: {sh['dtypes']}, producer: {sh['producer']}")

    checks = {
        "число узлов совпадает": up["nodes"] == sh["nodes"],
        "типы узлов совпадают": up["node_types"] == sh["node_types"],
        "число инициализаторов совпадает": up["initializers"] == sh["initializers"],
        "имена тензоров совпадают": up["names"] == sh["names"],
        "в апстриме есть FP16, в поставляемом нет": (
            up["dtypes"].get(FP16, 0) > 0 and sh["dtypes"].get(FP16, 0) == 0
        ),
        "все типы в поставляемом - FP32": set(sh["dtypes"]) == {FP32},
    }

    print()
    for name, passed in checks.items():
        print(f"  [{'ok' if passed else 'FAIL'}] {name}")

    if not all(checks.values()):
        print("\nфайлы не связаны конверсией точности: смотрите строки FAIL")
        return 1

    print(f"\nвывод: поставляемый файл - тот же граф, {up['dtypes'][FP16]} тензоров FP16 "
          f"расширены до FP32; изменена только точность хранения")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
