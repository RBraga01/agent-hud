# Changelog

## Unreleased

First working version. Runs in Raven's simulator; cannot be deployed to real
glasses until Raven issues credentials and opens their upload service.

### Added
- Reads a list of items from a gateway and shows how many need attention.
- A count in the right periphery. Stare at it and the detail opens; look away
  and stay away and it closes.
- Keeps the last known list when the gateway cannot be reached, with a
  separate marker, so an empty display and a broken one never look alike.
- A stub gateway that serves a file you can hand-edit while testing.
- Screen composed from the Raven Framework's own card and button components,
  using the theme's values rather than invented ones.

### Known limits
- Staring can only be tested with a mouse. Real eye tracking is accurate to
  two or three degrees, so the target may need to be larger than it looks.
- Text washes out over a bright sky. The display can only add light, and text
  is already at full white, so there is no headroom left.
- Voice is not built yet. It needs its own design first.
