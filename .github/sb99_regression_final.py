from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 match, got {count}')
    s = s.replace(old, new, 1)


def regex_once(pattern, replacement, label, flags=re.S):
    global s
    new_s, count = re.subn(pattern, replacement, s, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 regex match, got {count}')
    s = new_s

# ---------------------------------------------------------------------------
# Runtime state: do not trust stale camp build completion across executions.
# The world itself is authoritative and will be rescanned.
# ---------------------------------------------------------------------------
replace_once(
    '    campBuildInterval = 2,\n    lastCampBuild = 0,\n    campBuildRunning = false,\n    campBuildDone = type(G.SB99_CAMP_BUILD_DONE) == "table" and G.SB99_CAMP_BUILD_DONE or {},',
    '    campBuildInterval = 1,\n    lastCampBuild = 0,\n    campBuildRunning = false,\n    campBuildDone = {},\n    campBenchLevel = 1,',
    'camp build state reset'
)

# ---------------------------------------------------------------------------
# Tree discovery: current maps can nest foliage. Cache all actual tree models
# recursively instead of only direct Foliage/Landmarks children.
# ---------------------------------------------------------------------------
regex_once(
    r'local treeCache = \{\}\n\nlocal function rebuildTrees\(\).*?\nend\n\nrebuildTrees\(\)',
    r'''local treeCache = {}

local function rebuildTrees()
    table.clear(treeCache)

    local map = workspace:FindFirstChild("Map")
    if not map then
        return
    end

    local folders = {}
    local foliage = map:FindFirstChild("Foliage")
    local landmarks = map:FindFirstChild("Landmarks")
    if foliage then table.insert(folders, foliage) end
    if landmarks then table.insert(folders, landmarks) end

    local seen = {}
    for _, folder in ipairs(folders) do
        for _, object in ipairs(folder:GetDescendants()) do
            if object:IsA("Model") and not seen[object] then
                local name = object.Name
                local lower = string.lower(name)
                if name == "Small Tree"
                    or name == "TreeBig1"
                    or name == "TreeBig2"
                    or string.find(lower, "tree", 1, true) ~= nil then
                    seen[object] = true
                    table.insert(treeCache, object)
                end
            end
        end
    end
end

rebuildTrees()''',
    'recursive tree cache'
)

# ---------------------------------------------------------------------------
# Stronghold readiness: an enabled entry prompt exists before the real run is
# ready on some servers. Never let it steal Auto Farm movement on that signal.
# ---------------------------------------------------------------------------
regex_once(
    r'local function strongholdReady\(\).*?\nend\n\nlocal function releaseFarmForStronghold\(\)',
    r'''local function strongholdReady()
    local countdown = getStrongholdCountdownText()
    local normalized = string.lower(string.gsub(countdown, "%s+", ""))

    -- Real ready signals only. An enabled entry ProximityPrompt can exist while
    -- the Stronghold is still counting down and must not hijack Auto Farm.
    if normalized == "00s" or normalized == "0s" or normalized == "ready" then
        return true
    end
    return strongholdDoorOpen() or strongholdGateOpen()
end

local function releaseFarmForStronghold()''',
    'stronghold real readiness'
)

# Nearby chest toggle should obey its own state. Auto Farm still locks it ON,
# but turning it back on manually resumes the worker instead of requiring a
# complete script restart.
replace_once(
    'local function openNearbyChests()\n    if not state.autoFarm or state.strongholdControl then',
    'local function openNearbyChests()\n    if not state.autoChest or state.strongholdControl then',
    'chest toggle restart'
)

# ---------------------------------------------------------------------------
# Child rescue: prefer the game\'s normal prompt interaction first, then use
# RequestBagStoreItem as a fallback. Prefer Old Sack when present because the
# live client scripts use that inventory bag for the rescue flow.
# ---------------------------------------------------------------------------
replace_once(
    '                    preferred = isSack(item),',
    '                    preferred = item.Name == "Old Sack" and 2 or (isSack(item) and 1 or 0),',
    'prefer old sack'
)
replace_once(
    '        if a.preferred ~= b.preferred then\n            return a.preferred\n        end',
    '        if a.preferred ~= b.preferred then\n            return a.preferred > b.preferred\n        end',
    'numeric sack preference'
)

regex_once(
    r'local function storeChildInSack\(sack, child\).*?\nend\n\nlocal function getBaggedChildren\(\)',
    r'''local function storeChildInSack(sack, child)
    if not state.autoFarm
        or not state.autoChildRescue
        or state.strongholdControl
        or not sack
        or not sack.Parent
        or not child
        or not child.Parent then
        return false
    end

    local childName = child.Name
    local part = getPart(child)
    local character = getCharacter()
    if part and character then
        pcall(character.PivotTo, character, part.CFrame * CFrame.new(0, 0, 3))
        lockFarmCharacter()
        focusCameraAt(part.Position)
        task.wait(2)
    end

    -- Streaming can replace the model during the wait. Reacquire by name.
    child = reacquireChild(childName) or child
    if not child or not child.Parent then
        return false
    end

    equipOwnedItem(sack)
    local before = getSackStoredCount(sack)

    local function storedNow(currentChild)
        local after = getSackStoredCount(sack)
        if after > before or childStoredInItemBag(childName) then
            state.childRescueObserved[childName] = true
            return true
        end
        local characters = workspace:FindFirstChild("Characters")
        if not currentChild or not currentChild.Parent
            or (characters and not currentChild:IsDescendantOf(characters)) then
            state.childRescueObserved[childName] = true
            return true
        end
        return false
    end

    -- The live game rescue path is the child's ProximityInteraction. Fire that
    -- first with the sack equipped, then verify the bag replicated.
    local head = child:FindFirstChild("Head")
    local attachment = head and head:FindFirstChild("ProximityAttachment")
    local prompt = attachment and attachment:FindFirstChild("ProximityInteraction")
    if not (prompt and prompt:IsA("ProximityPrompt")) then
        prompt = child:FindFirstChildWhichIsA("ProximityPrompt", true)
    end

    if prompt then
        for _ = 1, 2 do
            firePromptNow(prompt)
            task.wait(0.18)
            child = reacquireChild(childName) or child
            if storedNow(child) then
                return true
            end
        end
    end

    if not isLive(RequestBagStoreItem) then
        refreshRemotes()
    end
    if not isLive(RequestBagStoreItem) then
        return storedNow(child)
    end

    for _ = 1, 3 do
        if not state.autoFarm or state.strongholdControl then
            return false
        end
        child = reacquireChild(childName) or child
        if storedNow(child) then
            return true
        end
        if not child or not child.Parent then
            return true
        end

        local ok, response = callUtilityRemote(RequestBagStoreItem, 1.5, sack, child)
        if ok and response ~= false then
            task.wait(0.2)
        end
        if storedNow(reacquireChild(childName) or child) then
            return true
        end
        task.wait(0.2)
    end

    return false
end

local function getBaggedChildren()''',
    'prompt-first child bagging'
)

replace_once(
    '        if next(usedBags) ~= nil then\n            dropChildrenAtCamp(usedBags)\n        end',
    '        if next(usedBags) ~= nil or #getBaggedChildren() > 0 then\n            dropChildrenAtCamp(usedBags)\n        end',
    'drop children from previous bag attempt'
)

# ---------------------------------------------------------------------------
# Camp builder: current game exposes bench upgrades beyond 4. Detect current
# level, keep the known bed hierarchy, discover extra bed blueprints, and
# continue multiple successful steps per pass instead of stopping after one.
# ---------------------------------------------------------------------------
regex_once(
    r'local function currentCraftingBenchLevel\(\).*?\nend\n\nlocal function getGroundPositionAroundCamp',
    r'''local function currentCraftingBenchLevel()
    local best = math.max(1, tonumber(state.campBenchLevel) or 1)

    local function scan(root)
        if not root then return end
        for _, object in ipairs(root:GetDescendants()) do
            local level = tonumber(string.match(object.Name, "^Crafting Bench (%d+)$"))
            if level then
                best = math.max(best, level)
            elseif string.find(string.lower(object.Name), "crafting bench", 1, true) then
                for _, attributeName in ipairs({ "Level", "BenchLevel", "CraftingLevel", "UpgradeLevel" }) do
                    local value = tonumber(object:GetAttribute(attributeName))
                    if value then best = math.max(best, value) end
                end
            end
        end
    end

    local campground = getCampground()
    if campground then
        for _, attributeName in ipairs({ "CraftingBenchLevel", "CraftingLevel", "BenchLevel" }) do
            local value = tonumber(campground:GetAttribute(attributeName))
            if value then best = math.max(best, value) end
        end
    end

    scan(campground)
    scan(workspace:FindFirstChild("Structures"))
    state.campBenchLevel = best
    return best
end

local function getGroundPositionAroundCamp''',
    'robust bench level detection'
)

regex_once(
    r'-- Confirmed game progression\..*?\nlocal function plantAvailableSaplings\(\)',
    r'''-- Camp progression. Known bed order is preserved, then newer bench tiers
-- and any additional bed blueprints are discovered from CraftingDatabase.
local BASE_CAMP_BUILD_QUEUE = {
    { kind = "bench", name = "Crafting Bench 2", benchLevel = 2 },
    { kind = "bed", name = "Old Bed", offset = Vector3.new(-22, 0, 15) },
    { kind = "bed", name = "Regular Bed", offset = Vector3.new(-30, 0, 0) },
    { kind = "bench", name = "Crafting Bench 3", benchLevel = 3 },
    { kind = "bed", name = "Good Bed", offset = Vector3.new(-22, 0, -15) },
    { kind = "bench", name = "Crafting Bench 4", benchLevel = 4 },
    { kind = "bed", name = "Giant Bed", offset = Vector3.new(0, 0, 32) },
}

local function getCampBuildQueue()
    local queue = {}
    local seen = {}
    local maxBench = 8 -- current live progression; database can extend this.

    for _, spec in ipairs(BASE_CAMP_BUILD_QUEUE) do
        table.insert(queue, spec)
        seen[spec.name] = true
    end

    local database = getCraftingDatabase()
    local blueprints = database and database.PossibleBlueprints
    local extraBeds = {}
    if type(blueprints) == "table" then
        for _, group in pairs(blueprints) do
            if type(group) == "table" then
                for _, blueprint in pairs(group) do
                    if type(blueprint) == "table" and type(blueprint.Name) == "string" then
                        local benchLevel = tonumber(string.match(blueprint.Name, "^Crafting Bench (%d+)$"))
                        if benchLevel then
                            maxBench = math.max(maxBench, benchLevel)
                        elseif string.find(string.lower(blueprint.Name), "bed", 1, true)
                            and not seen[blueprint.Name] then
                            table.insert(extraBeds, blueprint.Name)
                            seen[blueprint.Name] = true
                        end
                    end
                end
            end
        end
    end

    for level = 5, maxBench do
        local name = "Crafting Bench " .. tostring(level)
        if not seen[name] then
            table.insert(queue, { kind = "bench", name = name, benchLevel = level })
            seen[name] = true
        end
    end

    table.sort(extraBeds, function(a, b)
        local aw, as = getCraftCost(a)
        local bw, bs = getCraftCost(b)
        local ac = (aw or 0) + (as or 0)
        local bc = (bw or 0) + (bs or 0)
        if ac == bc then return a < b end
        return ac < bc
    end)

    for index, name in ipairs(extraBeds) do
        local angle = ((index - 1) / math.max(1, #extraBeds)) * math.pi * 2
        table.insert(queue, {
            kind = "bed",
            name = name,
            offset = Vector3.new(math.cos(angle) * 40, 0, math.sin(angle) * 40),
        })
    end

    return queue
end

local function markCampBuildDone(itemName)
    state.campBuildDone[itemName] = true
    G.SB99_CAMP_BUILD_DONE = state.campBuildDone
end

local function campBuildIsDone(spec)
    if spec.kind == "bench" then
        if currentCraftingBenchLevel() >= (spec.benchLevel or 1) then
            markCampBuildDone(spec.name)
            return true
        end
        return false
    end

    if worldHasCampStructure(spec.name) then
        markCampBuildDone(spec.name)
        return true
    end
    return false
end

local function runCampBuildService()
    if not state.active
        or not state.autoFarm
        or not state.smartResources
        or state.campBuildRunning
        or state.childRescueRunning
        or state.foodServiceRunning
        or state.resourceServiceRunning
        or not state.autoCampBuild
        or state.strongholdControl
        or isNight() then
        return
    end

    local fireLevel = getCampfireLevel()
    if fireLevel == nil or fireLevel < state.campfireTargetLevel then return end

    local now = os.clock()
    if now - state.lastCampBuild < state.campBuildInterval then return end
    state.lastCampBuild = now
    state.campBuildRunning = true

    local serviceOk = pcall(function()
        local campground = getCampground()
        if not campground then return end

        local completed = 0
        for _, spec in ipairs(getCampBuildQueue()) do
            if not state.active or not state.autoFarm or state.strongholdControl then
                break
            end

            if not campBuildIsDone(spec) then
                local item = spec.kind == "bed" and findOwnedNamedItem(spec.name) or nil

                if not item then
                    local woodCost, scrapCost = getCraftCost(spec.name)
                    if woodCost == nil or scrapCost == nil then return end

                    local totalWood = tonumber(campground:GetAttribute("TotalWood")) or 0
                    local totalScrap = tonumber(campground:GetAttribute("TotalScrap")) or 0
                    if totalWood < woodCost or totalScrap < scrapCost then
                        return
                    end

                    if not isLive(CraftItem) then refreshRemotes() end
                    if not isLive(CraftItem) then return end

                    local crafted, response = callUtilityRemote(CraftItem, 2, spec.name)
                    if not crafted or response == false then
                        return
                    end

                    if spec.kind == "bench" then
                        state.campBenchLevel = math.max(
                            tonumber(state.campBenchLevel) or 1,
                            tonumber(spec.benchLevel) or 1
                        )
                        markCampBuildDone(spec.name)
                        completed = completed + 1
                        task.wait(0.18)
                    else
                        local deadline = os.clock() + 3
                        repeat
                            task.wait(0.1)
                            item = findOwnedNamedItem(spec.name)
                        until item or not state.autoFarm or state.strongholdControl or os.clock() >= deadline
                        if not item then return end
                    end
                end

                if spec.kind == "bed" and item and item.Parent then
                    cancelFarmTween()
                    local character = getCharacter()
                    if character then
                        pcall(character.PivotTo, character, CFrame.new(CHILD_CAMP_DROP))
                    end
                    lockFarmCharacter()
                    task.wait(0.2)

                    if not placeCampStructure(item, spec.offset or Vector3.new(35, 0, 0)) then
                        return
                    end
                    markCampBuildDone(spec.name)
                    completed = completed + 1
                    task.wait(0.2)
                end

                -- Keep one pass responsive, but do more than the old single
                -- step so upgrades cannot appear to stop after Bench 2.
                if completed >= 4 then
                    return
                end
            end
        end
    end)

    state.campBuildRunning = false
    if not serviceOk then
        state.lastCampBuild = 0
    end
end

local function plantAvailableSaplings()''',
    'multi-stage camp builder'
)

# ---------------------------------------------------------------------------
# Auto Farm startup and direct tree dwell attack. This makes tree cutting
# deterministic even if the background combat cache has not refreshed yet.
# ---------------------------------------------------------------------------
replace_once(
    '    state.patrolExploreIndex = 0\n    table.clear(treeVisitCooldown)',
    '    state.patrolExploreIndex = 0\n    table.clear(treeVisitCooldown)\n    table.clear(attackCooldown)\n    rebuildTrees()\n    bestAxe = select(1, findBestOwned(axeScore))',
    'farm combat warm start'
)

replace_once(
    '''                    if point and moveFarmTo(point, false) then
                        -- Brief dwell gives Auto Chop/Kill Aura/chest prompting
                        -- time to act while keeping daytime traversal continuous.
                        task.wait(tree and 0.55 or 0.25)
                    else
                        task.wait(0.1)
                    end''',
    '''                    if point and moveFarmTo(point, false) then
                        if tree and tree.Parent and state.autoChop then
                            -- Directly service the selected Small Tree while the
                            -- normal aura worker keeps handling nearby trees/enemies.
                            local chopDeadline = os.clock() + 1.1
                            repeat
                                attackTarget(tree, true)
                                task.wait(0.08)
                            until not state.autoFarm
                                or state.strongholdControl
                                or not smallTreeAvailable(tree)
                                or os.clock() >= chopDeadline
                        else
                            task.wait(0.25)
                        end
                    else
                        task.wait(0.1)
                    end''',
    'direct selected tree chop'
)

# ---------------------------------------------------------------------------
# Mobile UI: full viewport drag, deterministic section/header ordering, and a
# slightly shorter panel. The previous section layout used Name sorting, which
# is why content could render above its category header after restore.
# ---------------------------------------------------------------------------
replace_once('screen.IgnoreGuiInset = false', 'screen.IgnoreGuiInset = true', 'ignore inset for drag')
replace_once('frame.Size = UDim2.fromOffset(286, 430)', 'frame.Size = UDim2.fromOffset(300, 420)', 'mobile panel size')
replace_once('frame.Position = UDim2.new(0.5, -143, 0, 6)', 'frame.Position = UDim2.new(0.5, -150, 0, 8)', 'mobile panel position')
replace_once('scroll.ScrollBarThickness = 3\nscroll.CanvasSize', 'scroll.ScrollBarThickness = 3\nscroll.Active = true\nscroll.CanvasSize', 'scroll touch activation')

replace_once(
    '    holder.BorderSizePixel = 0\n    holder.Parent = scroll',
    '    holder.BorderSizePixel = 0\n    holder.LayoutOrder = #scroll:GetChildren() + 1\n    holder.Parent = scroll',
    'section root order'
)
replace_once(
    '    local layout = Instance.new("UIListLayout")\n    layout.Padding = UDim.new(0, 4)\n    layout.Parent = holder',
    '    local layout = Instance.new("UIListLayout")\n    layout.Padding = UDim.new(0, 4)\n    layout.SortOrder = Enum.SortOrder.LayoutOrder\n    layout.Parent = holder',
    'section layout order'
)
replace_once(
    '    head.TextSize = 10\n    head.TextXAlignment = Enum.TextXAlignment.Left\n    head.Parent = holder',
    '    head.TextSize = 10\n    head.TextXAlignment = Enum.TextXAlignment.Left\n    head.LayoutOrder = 1\n    head.Parent = holder',
    'section header order'
)
replace_once(
    '    content.AutomaticSize = Enum.AutomaticSize.Y\n    content.BackgroundTransparency = 1\n    content.Parent = holder\n    local list = Instance.new("UIListLayout")\n    list.Padding = UDim.new(0, 4)\n    list.Parent = content',
    '    content.AutomaticSize = Enum.AutomaticSize.Y\n    content.BackgroundTransparency = 1\n    content.LayoutOrder = 2\n    content.Parent = holder\n    local list = Instance.new("UIListLayout")\n    list.Padding = UDim.new(0, 4)\n    list.SortOrder = Enum.SortOrder.LayoutOrder\n    list.Parent = content',
    'section content order'
)
replace_once(
    '    button.TextSize = 9\n    button.TextXAlignment = Enum.TextXAlignment.Left\n    button.Parent = parent',
    '    button.TextSize = 9\n    button.TextXAlignment = Enum.TextXAlignment.Left\n    button.LayoutOrder = #parent:GetChildren() + 1\n    button.Parent = parent',
    'toggle order'
)

replace_once(
    '        local widthScale = (viewport.X - 8) / 286\n        local heightScale = (viewport.Y - 8) / 430',
    '        local widthScale = (viewport.X - 8) / 300\n        local heightScale = (viewport.Y - 8) / 420',
    'responsive dimensions'
)

regex_once(
    r'local dragging, dragInput, dragTouch, dragStart, frameStart = false, nil, nil, nil, nil.*?\n\nlocal ballDragging,',
    r'''local dragging = false
local dragTouch = nil
local dragStart = nil
local frameStart = nil

local function beginFrameDrag(input)
    if input.UserInputType ~= Enum.UserInputType.MouseButton1
        and input.UserInputType ~= Enum.UserInputType.Touch then
        return
    end

    dragging = true
    dragTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
    dragStart = Vector2.new(input.Position.X, input.Position.Y)
    frameStart = Vector2.new(frame.AbsolutePosition.X, frame.AbsolutePosition.Y)
end

track(header.InputBegan:Connect(beginFrameDrag))
track(status.InputBegan:Connect(beginFrameDrag))

track(UserInputService.InputChanged:Connect(function(input)
    if not dragging or not dragStart or not frameStart then return end

    if dragTouch then
        if input ~= dragTouch then return end
    elseif input.UserInputType ~= Enum.UserInputType.MouseMovement then
        return
    end

    local current = Vector2.new(input.Position.X, input.Position.Y)
    local desired = frameStart + (current - dragStart)
    local p = clampToViewport(desired, frame.AbsoluteSize)
    frame.Position = UDim2.fromOffset(p.X, p.Y)
end))

track(UserInputService.InputEnded:Connect(function(input)
    local ended = dragging and (
        (dragTouch and input == dragTouch)
        or (not dragTouch and input.UserInputType == Enum.UserInputType.MouseButton1)
    )
    if ended then
        dragging = false
        dragTouch = nil
        dragStart = nil
        frameStart = nil
    end
end))

local ballDragging,''',
    'robust main UI drag'
)

# Rework minimized-ball drag with the same global-input approach so restoring
# the panel cannot leave a stale touch owner.
regex_once(
    r'local ballDragging, ballInput, ballTouch, ballStart, ballPos, ballMoved = false, nil, nil, nil, nil, false.*?\n\ntask.spawn\(function\(\)',
    r'''local ballDragging = false
local ballTouch = nil
local ballStart = nil
local ballPos = nil
local ballMoved = false

track(ball.InputBegan:Connect(function(input)
    if input.UserInputType ~= Enum.UserInputType.MouseButton1
        and input.UserInputType ~= Enum.UserInputType.Touch then
        return
    end
    ballDragging = true
    ballMoved = false
    ballTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
    ballStart = Vector2.new(input.Position.X, input.Position.Y)
    ballPos = Vector2.new(ball.AbsolutePosition.X, ball.AbsolutePosition.Y)
end))

track(UserInputService.InputChanged:Connect(function(input)
    if not ballDragging or not ballStart or not ballPos then return end
    if ballTouch then
        if input ~= ballTouch then return end
    elseif input.UserInputType ~= Enum.UserInputType.MouseMovement then
        return
    end

    local current = Vector2.new(input.Position.X, input.Position.Y)
    local delta = current - ballStart
    if delta.Magnitude > 6 then ballMoved = true end
    local p = clampToViewport(ballPos + delta, ball.AbsoluteSize)
    ball.Position = UDim2.fromOffset(p.X, p.Y)
end))

track(UserInputService.InputEnded:Connect(function(input)
    local ended = ballDragging and (
        (ballTouch and input == ballTouch)
        or (not ballTouch and input.UserInputType == Enum.UserInputType.MouseButton1)
    )
    if not ended then return end
    ballDragging = false
    ballTouch = nil
    ballStart = nil
    ballPos = nil
    if not ballMoved and ball.Visible then restoreUI() end
end))

task.spawn(function()''',
    'robust minimized ball drag'
)

# Make status more useful and less noisy.
replace_once(
    '            "Godmode ON | Fire %s/6 | Radius %d\\n%s | Diamonds %s",',
    '            "Fire %s/6  |  Farm %dst  |  %s\\nDiamonds %s",',
    'compact status text'
)

TARGET.write_text(s, encoding='utf-8')
print('patched', TARGET)
