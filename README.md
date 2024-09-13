# Lambdalib

Lambdalib is a collection of cores, helpers and tools for [Amaranth](https://github.com/amaranth-lang/amaranth) created and maintained by [LambdaConcept](https://lambdaconcept.com/). It currently supports Amaranth 0.4.

Install
=======

```bash
pdm install
pdm install -d # Add development dependencies (eg. pytest)
```

Build some examples
===================

```bash
pdm run python examples/spi_bridge.py
pdm run python examples/i2c_bridge.py
```

Run tests
==============

```bash
pdm run pytest
```
