# Minecraft Redirect Proxy

This is a Minecraft proxy server that allows any Minecraft client to connect to any remote server without revealing the client's IP address. It would be useful for individuals who want to hide their IP address using a remote proxy.

This project is using Quarry, a Python library that implements the Minecraft protocol.

## Usage

First, you need to install Quarry:

```bash
pip3 install -r requirements.txt
```

Then, you can start the proxy server by running the following command:

```bash
python3 redirect_proxy.py -p 25565
```

After that, if you connect to the proxy server at `localhost:25565`, you will be redirected to the `minehut.com` by default. The proxy is listening on port 2556**6** by default. You can change the port by flag `-p` or `--port`.

```
optional arguments:
  -h, --help            show this help message and exit
  -a LISTEN_HOST1, --listen-host1 LISTEN_HOST1
                        address to listen on
  -p LISTEN_PORT1, --listen-port1 LISTEN_PORT1
                        port to listen on
  -b PASS_THROUGH_HOST, --pass-through-host PASS_THROUGH_HOST
                        address to connect to in dedicated mode
  -q PASS_THROUGH_PORT, --pass-through-port PASS_THROUGH_PORT
                        port to connect to in dedicated mode
  -c HIDDEN_CONNECT_HOST, --hidden-connect-host HIDDEN_CONNECT_HOST
                        another address to connect to in hidden mode
  -r HIDDEN_CONNECT_PORT, --hidden-connect-port HIDDEN_CONNECT_PORT
                        another port to connect to in hidden mode
  -d DOMAIN, --domain DOMAIN
                        the domain the proxy is running on
  -m {pass-through-dedicated,pass-through-by-domain,hidden}, --mode {pass-through-dedicated,pass-through-by-domain,hidden}
                        proxy mode
  --sync                sync motd with pass through host (default)
  --no-sync
```

## Proxy Mode

### Pass through dedicated

This mode allows any Minecraft client to connect to a dedicated server through the proxy.Here is an example of how to use this mode:

```bash 
python3 redirect_proxy.py -b mc.hypixel.net
```


### Pass through by domain

This mode allows any Minecraft client to connect to any remote server through the proxy. Here is an example of how to use this mode:

```bash
python3 redirect_proxy.py -m pass-through-by-domain -d server.domain
```

Assume the proxy is hosting at `server.domain`. When the client connects to the following address, it will actually connect to:

`host.com.server.domain` -> `host.com` on port 25565<br/>
`my.host.com.server.domain` -> `my.host.com` on port 25565<br/>
`12.34.56.78.server.domain` -> `12.34.56.78` on port 25565

The port number can also be included in the address, for example:

`host.com.25565.server.domain` -> `host.com` on port 25565<br/>
`my.host.com.3000.server.domain` -> `my.host.com` on port 3000<br/>
`12.34.56.78.100.server.domain` -> `12.34.56.78` on port 100


### Hidden

This mode allows any Minecraft client to connect to a dedicated server through the proxy without the client knowing. Here is an example of how to use this mode:

```bash
python3 redirect_proxy.py -m hidden -c connect.2b2t.org
```

Notice that SRV record resolution is not supported in this mode.


## Similar Projects

https://github.com/cunnie/sslip.io

https://github.com/RenegadeEagle/minecraft-redirect-proxy

https://gitlab.com/minekloud/minecraft-gateway

https://github.com/itzg/mc-router