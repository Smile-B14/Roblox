-- Smile B RNG loader / hotfix
-- Loads the last full state-machine build and patches the character-facing code
-- so the script never writes HumanoidRootPart.CFrame directly.

local BASE_URL = "https://raw.githubusercontent.com/Smile-B14/Roblox/f502f70903337c0ea95e8ae08220becdb3769072/rng_auto_buyer.lua"

local ok, source = pcall(function()
    return game:HttpGet(BASE_URL)
end)

if not ok or type(source) ~= "string" then
    warn("[SmileB RNG] Failed to download core script:", source)
    return
end

local oldFaceTarget = [[local function FaceTarget(pos)
    if not Root or not pos then return end
    local flat=Vector3.new(pos.X,Root.Position.Y,pos.Z)
    if (flat-Root.Position).Magnitude>.01 then pcall(function() Root.CFrame=CFrame.lookAt(Root.Position,flat) end) end
end]]

local newFaceTarget = [[local function FaceTarget(pos)
    -- SAFETY FIX:
    -- Never write HumanoidRootPart.CFrame just to face a prompt.
    -- Repeated client-side root transforms can trigger movement validation
    -- and cause the server to reset/kill the character after several spins.
    -- Character movement stays fully on Humanoid:MoveTo/pathfinding.
    -- AimCameraFor handles looking at prompts without moving the character root.
    return
end]]

local startPos, endPos = source:find(oldFaceTarget, 1, true)
if startPos then
    source = source:sub(1, startPos - 1) .. newFaceTarget .. source:sub(endPos + 1)
else
    warn("[SmileB RNG] FaceTarget hotfix pattern not found; refusing to run unsafe core")
    return
end

local oldVersion = 'local VERSION = "2026-08-09-ready-lock-v1"'
local newVersion = 'local VERSION = "2026-08-09-ready-lock-v2-no-root-cframe"'
local vs, ve = source:find(oldVersion, 1, true)
if vs then
    source = source:sub(1, vs - 1) .. newVersion .. source:sub(ve + 1)
end

local fn, compileErr = loadstring(source)
if not fn then
    warn("[SmileB RNG] Core compile failed:", compileErr)
    return
end

local success, runtimeErr = pcall(fn)
if not success then
    warn("[SmileB RNG] Core runtime failed:", runtimeErr)
    return
end

print("[SmileB RNG] Safety hotfix active: no HumanoidRootPart CFrame writes")
