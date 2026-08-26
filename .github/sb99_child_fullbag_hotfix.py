from pathlib import Path
p = Path('99 Nights Helper Godmode')
s = p.read_text(encoding='utf-8')
old1 = '''local function isStorageBag(item)
    if not item or not item.Parent then
        return false
    end
    local capacity = tonumber(item:GetAttribute("Capacity"))
    local count = tonumber(item:GetAttribute("NumberItems"))
    return capacity ~= nil and count ~= nil and capacity > count
end'''
new1 = '''local function isStorageBag(item)
    if not item or not item.Parent then
        return false
    end
    local capacity = tonumber(item:GetAttribute("Capacity"))
    local count = tonumber(item:GetAttribute("NumberItems"))
    -- Include full bags in discovery so children left in a previous/full bag
    -- can still be dropped at camp. Pickup selection separately requires space.
    return capacity ~= nil and capacity > 0 and count ~= nil and count >= 0
end'''
old2 = '''local function chooseRescueSack(requiredSlots)
    local bags = getRescueBags(requiredSlots)
    local first = bags[1]
    return first and first.item or nil, first and first.free or 0
end'''
new2 = '''local function chooseRescueSack(requiredSlots)
    local bags = getRescueBags(requiredSlots)
    local first = bags[1]
    if not first or first.free < requiredSlots then
        return nil, 0
    end
    return first.item, first.free
end'''
for old, new, name in [(old1,new1,'bag discovery'),(old2,new2,'bag selection')]:
    if s.count(old) != 1:
        raise RuntimeError(f'{name}: expected 1 match, got {s.count(old)}')
    s = s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
