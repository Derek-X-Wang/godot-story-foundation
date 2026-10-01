-- Test-only adapter substitution fixture, using first-party synthetic PNG pixels.
local f=assert(io.open(assert(app.params['manifest']), 'r'))
local m=json.decode(f:read('*a')); f:close()
local sheet=Image{fromFile=assert(app.params['png'])}
local indexed=app.params['indexed']=='true'
local mode=indexed and ColorMode.INDEXED or ColorMode.RGB
local s=Sprite(m.cell[1],m.cell[2],mode)
local colorIndex={}
if indexed then
  local palette=Palette(#m.palette)
  for n,c in ipairs(m.palette) do
    local r=tonumber(c:sub(2,3),16);local g=tonumber(c:sub(4,5),16)
    local b=tonumber(c:sub(6,7),16);local a=tonumber(c:sub(8,9),16)
    palette:setColor(n-1,Color{r=r,g=g,b=b,a=a})
    colorIndex[app.pixelColor.rgba(r,g,b,a)]=n-1
  end
  s:setPalette(palette);s.transparentColor=0
end
s.layers[1].name='Authored pixels'
local count=0
for _,tag in ipairs(m.tags) do
  for _,duration in ipairs(tag.durations_ms) do
    count=count+1
    if count>1 then s:newEmptyFrame() end
    s.frames[count].duration=duration/1000
    local x=((count-1)%m.columns)*m.cell[1]
    local y=math.floor((count-1)/m.columns)*m.cell[2]
    local im=Image(m.cell[1],m.cell[2],mode)
    if indexed then
      for py=0,m.cell[2]-1 do for px=0,m.cell[1]-1 do
        im:drawPixel(px,py,assert(colorIndex[sheet:getPixel(x+px,y+py)]))
      end end
    else im:drawImage(sheet,Point(-x,-y)) end
    if s.layers[1]:cel(count) then s:deleteCel(s.layers[1],count) end
    s:newCel(s.layers[1],count,im,Point(0,0))
  end
  local native=s:newTag(tag.start+1,tag.start+tag.count)
  native.name=tag.name
end
local slice=s:newSlice(Rectangle(0,0,m.cell[1],m.cell[2]))
slice.name='cell'; slice.pivot=Point(m.pivot[1],m.pivot[2])
s:saveAs(assert(app.params['output']));s:close()
