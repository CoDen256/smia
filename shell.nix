{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python312
    zlib
  ];
  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    if [ ! -d .venv ]; then
      python -m venv .venv
    fi
    source .venv/bin/activate
    pip install -r requirements.txt --quiet
  '';
}
