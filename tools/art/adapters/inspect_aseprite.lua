-- Read-only native inspection. Source is never saved, flattened or overwritten.
-- Character-specific generation scripts/rigs are deliberately not executed here.
local s = Sprite{fromFile=assert(app.params['source'])}
local result = {cell={s.width,s.height}, durations_ms={}, layers={}, palettes={}}
for n=1,#s.frames do
  local frame=s.frames[n]
  result.durations_ms[#result.durations_ms+1] = math.floor(frame.duration * 1000 + 0.5)
end
local function layers(list)
  for n=1,#list do
    local layer=list[n]
    result.layers[#result.layers+1] = layer.name
    if layer.isGroup then layers(layer.layers) end
  end
end
layers(s.layers)
-- Record every palette exposed by the API; animated palettes are not supported.
for n=1,#s.palettes do
  local palette=s.palettes[n]
  local colors = {}
  for i=0,#palette-1 do
    local c=palette:getColor(i)
    if s.colorMode==ColorMode.INDEXED and i==s.transparentColor then
      colors[#colors+1] = '#00000000'
    else
      colors[#colors+1] = string.format('#%02x%02x%02x%02x',c.red,c.green,c.blue,c.alpha)
    end
  end
  result.palettes[#result.palettes+1] = colors
end
result.color_mode = s.colorMode==ColorMode.INDEXED and 'indexed' or s.colorMode==ColorMode.RGB and 'rgba' or 'grayscale'
local file=assert(io.open(assert(app.params['output']), 'w'))
file:write(json.encode(result)); file:close(); s:close()
