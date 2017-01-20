## REST API Specification for Config

### Resource: Config

**URI:** /config

Contains information about the application environment and configuration.

**Methods:**

* **GET**: Retrieve configuration information
    * proxy_port: SSL port to list on
    * websockets_port: Port for websocket proxy to listen on
    * auth: Authentication method used to log in to Wok
    * version: Wok version
* **POST**: *See Task Actions*

**Actions (POST):**

*No actions defined*

#### Examples
GET /config
{
 proxy_port: 8001,
 websockets_port: 64667,
 version: 2.0
}

### Collection: Plugins

**URI:** /config/plugins

**Methods:**

* **GET**: Retrieve a summarized list of all UI Plugins.

#### Examples
GET /plugins
[{'name': 'pluginA', 'enabled': True}, {'name': 'pluginB', 'enabled': False}]

### Resource: Plugins

**URI:** /config/plugins/*:name*

Represents the current state of a given WoK plug-in.

**Methods:**

* **GET**: Retrieve the state of the plug-in.
    * name: The name of the plug-in.
    * enabled: True if the plug-in is currently enabled in WoK, False otherwise.

* **POST**: *See Plugin Actions*

**Actions (POST):**

* enable: Enable the plug-in in the configuration file.
* disable: Disable the plug-in in the configuration file.
