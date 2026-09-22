# Integration patches

The gateway is designed to drop into the upstream Deekseep source tree with no
changes to its call sites. Only three feature gates need to be opened.

## 1. `BuildInfo.LOCAL_API_INCLUDED`

The upstream build script generates `BuildInfo.java` with:

```java
public static final boolean LOCAL_API_INCLUDED = false;
```

Set it to `true`. Keep `PROTECTED_BUILD = false`: that keeps the runtime
protection and license-server checks inert while the gateway runs.

## 2. `Main.startz1` license re-enrollment

`startz1` re-enrolls with the license server before resolving the gateway:

```java
if (!CloudPromptClient.hasLocalApiGrant(appContext)) {
    CloudPromptClient.activate(appContext, ...);
    return;
}
```

An open build has no license server, so this always returns early and the
gateway never starts. Guard it with `BuildInfo.PROTECTED_BUILD`:

```java
if (BuildInfo.PROTECTED_BUILD && !CloudPromptClient.hasLocalApiGrant(appContext)) {
```

## 3. `DeekseepUi` menu entries

Both Local API settings entries are hidden behind `PROTECTED_BUILD`:

```java
if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED && !isClosedV241()) {
if (BuildInfo.PROTECTED_BUILD && BuildInfo.LOCAL_API_INCLUDED) {
```

Drop the `PROTECTED_BUILD` conjunct in those two conditions only. Leave
`isClosedV241()` alone — it selects a version-specific behaviour for the
DeepSeek 2.4.1 host.

`docs/build-local-api.sh` applies all three automatically.
