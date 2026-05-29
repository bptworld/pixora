metadata {
    definition(
        name: "ESPHome Bridge Omni",
        namespace: "pixora",
        author: "Pixora"
    ) {
        capability "Actuator"
        capability "Sensor"
        capability "Switch"
        capability "Motion Sensor"
        capability "Contact Sensor"
        capability "Presence Sensor"
        capability "Water Sensor"
        capability "Refresh"

        attribute "value", "string"
        attribute "numberValue", "number"
        attribute "textValue", "string"
        attribute "lastUpdated", "string"

        command "setAttributeValue", [
            [name: "attributeName", type: "STRING", description: "Attribute name"],
            [name: "attributeValue", type: "STRING", description: "Attribute value"]
        ]
        command "setValue", [[name: "attributeValue", type: "STRING"]]
        command "setNumber", [[name: "attributeValue", type: "NUMBER"]]
        command "setText", [[name: "attributeValue", type: "STRING"]]
        command "active"
        command "inactive"
        command "open"
        command "close"
        command "present"
        command "notPresent"
        command "wet"
        command "dry"
    }
}

void installed() {
    initialize()
}

void updated() {
    initialize()
}

void initialize() {
    sendEvent(name: "switch", value: device.currentValue("switch") ?: "off")
}

void refresh() {
    touch()
}

void on() {
    sendEvent(name: "switch", value: "on")
    touch()
}

void off() {
    sendEvent(name: "switch", value: "off")
    touch()
}

void active() {
    sendEvent(name: "motion", value: "active")
    touch()
}

void inactive() {
    sendEvent(name: "motion", value: "inactive")
    touch()
}

void open() {
    sendEvent(name: "contact", value: "open")
    touch()
}

void close() {
    sendEvent(name: "contact", value: "closed")
    touch()
}

void present() {
    sendEvent(name: "presence", value: "present")
    touch()
}

void notPresent() {
    sendEvent(name: "presence", value: "not present")
    touch()
}

void wet() {
    sendEvent(name: "water", value: "wet")
    touch()
}

void dry() {
    sendEvent(name: "water", value: "dry")
    touch()
}

void setValue(String attributeValue) {
    sendEvent(name: "value", value: attributeValue)
    touch()
}

void setNumber(BigDecimal attributeValue) {
    sendEvent(name: "numberValue", value: attributeValue)
    touch()
}

void setText(String attributeValue) {
    sendEvent(name: "textValue", value: attributeValue)
    touch()
}

void setAttributeValue(String attributeName, String attributeValue) {
    sendEvent(name: attributeName, value: attributeValue)
    touch()
}

private void touch() {
    sendEvent(name: "lastUpdated", value: new Date().format("yyyy-MM-dd HH:mm:ss", location.timeZone))
}
