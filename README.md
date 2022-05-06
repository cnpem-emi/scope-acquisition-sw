# Scope Acquisition Software

Basic functions to automate gathering power supply buffer data

## Usage

As a module:

```python
save_data(path="/save/path")
```

As a standalone file:

```bash
python3 acquire.py
```

## Caveats

- The acquiring routine (`acquire.py`) is meant to run on Python versions 3.6.1 and later. However, the graphical plot script was only tested on Python 3.6.1 and 3.6.8. Further Python versions require different code (tag `>3.7`)

