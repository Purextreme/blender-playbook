# Display attribute colors without lighting

## Applicability

Use when mesh, curve, or point-cloud colors should reproduce source imagery directly and must not react to Blender lights.

## Core conclusions

- Feed the named color attribute into an Emission shader with strength `1.0`.
- Emission removes light dependence but does not bypass color management.
- For ordinary 8-bit image-derived RGB, convert sRGB values to linear before feeding the shader, then display with an sRGB/Standard pipeline.
- A point cloud may need Geometry Nodes `Set Material` because it lacks normal mesh material slots.

## Recommended display pipeline

1. Store shader-facing color as point- or corner-domain `FLOAT_COLOR` in linear space.
2. Read it with a named attribute node.
3. Connect Color to Emission Color and Emission to Material Output.
4. Use Emission Strength `1.0`.
5. Set display device to `sRGB`, view transform to `Standard`, look to `None`, exposure to `0`, and gamma to `1`.
6. Set the World background strength to `0` when a black background is desired.
7. In Rendered viewport mode, disable scene-light usage. Lighting should not affect the result.

The standard sRGB decoding function is:

```python
linear = srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4
```

## Decision points

- Use the source's declared transfer function when known; do not assume every numeric color attribute is sRGB.
- Use `Standard` for direct source-color comparison. AgX is useful for scene rendering but intentionally changes display mapping.
- Keep Emission at `1.0` for faithful reproduction. Raise it only when the user explicitly wants artistic amplification or bloom.
- Hide overlays only for visual verification; overlays do not change rendered color.

## Common pitfalls

- “No lights” does not automatically mean “correct source color.” Color-space conversion still matters.
- Raw `byte / 255` values from an sRGB image are not linear shader values.
- `Solid / Vertex` can provide a quick inspection but may not match the shader/render pipeline.
- A black World does not darken Emission; it only controls the background and non-emissive environment contribution.

## Verification

- Toggle or disable all Blender lights; the object colors must remain unchanged.
- Inspect color-management settings inside Blender rather than assuming defaults.
- Capture a Rendered viewport screenshot with overlays off and compare it to the source image.
- Check representative dark, neutral, and saturated regions rather than judging only the global average.

## Provenance

Verified on Blender 5.2.0 LTS while matching a colored GLB point cloud to its original reference frame.
