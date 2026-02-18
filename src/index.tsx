import {
    ButtonItem,
    definePlugin,
    PanelSection,
    PanelSectionRow,
    ToggleField,
    Router,
    ServerAPI,
    staticClasses,
    Dropdown,
    DropdownOption,
    SingleDropdownOption,
    SliderField
} from "decky-frontend-lib";
import { VFC, useState, useEffect, useRef } from "react";
import { RiTvLine } from "react-icons/ri";

declare global {
    interface Window {
        SteamClient: any;
    }
}

// ---- Types ----
interface ShaderParam {
    name: string;
    type: string; // "float" | "bool" | "int"
    default: number | boolean;
    value: number | boolean;
    ui_type?: string;
    ui_min?: number;
    ui_max?: number;
    ui_step?: number;
    ui_label?: string;
    ui_items?: string[];
}

// ---- Display helpers ----
/** Replace underscores with spaces and strip any trailing " [ShaderName]" bracket from labels */
const formatDisplayName = (name: string): string =>
    name.replace(/\.fx$/i, "").replace(/_/g, " ").replace(/\s*\[.*?\]\s*$/, "").trim();

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
    const baseShader = { data: "None", label: "No Shader" } as SingleDropdownOption;
    const [shadersEnabled, setShadersEnabled] = useState<boolean>(false);
    const [selectedShader, setSelectedShader] = useState<DropdownOption>(baseShader);
    const [shaderOptions, setShaderOptions] = useState<DropdownOption[]>([baseShader]);
    const [currentGameName, setCurrentGameName] = useState<string>("Unknown");
    const [shaderParams, setShaderParams] = useState<ShaderParam[]>([]);
    const paramTimeouts = useRef<{ [key: string]: number }>({});
    const [applyDisabled, setApplyDisabled] = useState(false);
    const [perGame, setPerGame] = useState<boolean>(false);

    const getShaderOptions = (shaderList: string[]): DropdownOption[] => [
        baseShader,
        ...shaderList.map(s => ({ data: s, label: formatDisplayName(s) } as SingleDropdownOption))
    ];

    const fetchShaderParams = async () => {
        const resp = await serverAPI.callPluginMethod("get_shader_params", {});
        if (resp.result && Array.isArray(resp.result)) {
            setShaderParams(resp.result as ShaderParam[]);
        } else {
            setShaderParams([]);
        }
    };

    const initState = async () => {
        // 1. Send active app info to backend
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
        await serverAPI.callPluginMethod("set_current_game_info", { appid, appname });

        // 2. Refresh info from backend (gets resolved ID like 'steamos' and per-game status)
        const info = (await serverAPI.callPluginMethod("get_game_info", {})).result as any;
        setCurrentAppId(info.appid);
        setCurrentGameName(info.appname);
        setPerGame(info.per_game);

        // 3. Get shader list
        const shaderList = (await serverAPI.callPluginMethod("get_shader_list", {})).result as string[];
        const options = getShaderOptions(shaderList);
        setShaderOptions(options);

        // 4. Get enabled status
        let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        let isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        // 5. Get current shader
        let curr = await serverAPI.callPluginMethod("get_current_shader", {});
        let targetData = curr.result;
        if (targetData === "0") targetData = "None";

        // Find the matched option to ensure referential equality, which fixes the dropdown scroll position
        const matchedOption = options.find(o => o.data === targetData);
        if (matchedOption) {
            setSelectedShader(matchedOption);
        } else {
            setSelectedShader({
                data: targetData,
                label: targetData === "None" ? "None" : formatDisplayName(targetData as string)
            } as SingleDropdownOption);
        }

        // 6. Fetch params
        await fetchShaderParams();
    }

    // --- Init state on mount ---
    useEffect(() => {
        initState();
    }, []);

    // --- Poll for game changes and re-init state ---
    useEffect(() => {
        let lastAppId = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const interval = setInterval(async () => {
            const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
            if (appid !== lastAppId) {
                lastAppId = appid;
                await initState();
            }
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    // --- Helper to auto-apply the shader (forces gamescope reload) ---
    const applyShader = async () => {
        await serverAPI.callPluginMethod("apply_shader", {});
    };

    // --- Helper to debounce parameter changes with auto-apply ---
    const handleParamChange = (paramName: string, value: number | boolean) => {
        // Update local state immediately for responsive UI
        setShaderParams(prev => prev.map(p =>
            p.name === paramName ? { ...p, value } : p
        ));
        // Debounce the backend call + auto-apply
        if (paramTimeouts.current[paramName]) {
            clearTimeout(paramTimeouts.current[paramName]);
        }
        paramTimeouts.current[paramName] = window.setTimeout(async () => {
            await serverAPI.callPluginMethod("set_shader_param", { name: paramName, value });
            await applyShader();
        }, 500);
    };

    // --- Render a single parameter control ---
    const renderParam = (p: ShaderParam) => {
        const isDisabled = !shadersEnabled || selectedShader.data === "None";

        if (p.type === "bool") {
            return (
                <PanelSectionRow key={p.name}>
                    <ToggleField
                        label={formatDisplayName(p.ui_label || p.name)}
                        checked={p.value as boolean}
                        disabled={isDisabled}
                        onChange={(checked: boolean) => {
                            handleParamChange(p.name, checked);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        // Combo / radio: render as dropdown with named options
        if (p.ui_items && p.ui_items.length > 0 && (p.ui_type === "combo" || p.ui_type === "radio")) {
            const comboOptions: DropdownOption[] = p.ui_items.map((label, idx) => ({
                data: idx,
                label: label,
            } as SingleDropdownOption));
            const currentIdx = typeof p.value === "number" ? p.value : 0;
            const selectedOption = comboOptions[currentIdx] || comboOptions[0];

            return (
                <PanelSectionRow key={p.name}>
                    <div style={{ marginBottom: "4px", fontSize: "12px" }}>
                        {formatDisplayName(p.ui_label || p.name)}
                    </div>
                    <Dropdown
                        menuLabel={formatDisplayName(p.ui_label || p.name)}
                        strDefaultLabel={selectedOption?.label as string || "Unknown"}
                        rgOptions={comboOptions}
                        selectedOption={selectedOption}
                        disabled={isDisabled}
                        onChange={(opt: DropdownOption) => {
                            handleParamChange(p.name, opt.data as number);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        if (p.type === "float" || p.type === "int") {
            const uiMin = p.ui_min ?? 0;
            const uiMax = p.ui_max ?? 2;
            const uiStep = p.ui_step ?? 0.01;

            // SliderField works with integer steps internally. We map the
            // float range [ui_min, ui_max] onto integer ticks.
            const numSteps = Math.round((uiMax - uiMin) / uiStep);
            const currentTick = Math.round(((p.value as number) - uiMin) / uiStep);

            return (
                <PanelSectionRow key={p.name}>
                    <SliderField
                        bottomSeparator="none"
                        label={`${formatDisplayName(p.ui_label || p.name)}: ${(p.value as number).toFixed(2)}`}
                        min={0}
                        max={numSteps}
                        step={1}
                        value={currentTick}
                        disabled={isDisabled}
                        onChange={(tick: number) => {
                            const real = uiMin + tick * uiStep;
                            // Clamp to avoid float drift
                            const clamped = Math.min(uiMax, Math.max(uiMin, parseFloat(real.toFixed(6))));
                            handleParamChange(p.name, clamped);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        return null; // unsupported type (e.g. combo with single option)
    };

    const hasParams = shaderParams.length > 0;

    return (
        <div>

            <PanelSection title="Profile">
                <PanelSectionRow>
                    <ToggleField
                        label="Per-Game Profile"
                        checked={perGame}
                        onChange={async (checked: boolean) => {
                            setPerGame(checked);
                            await serverAPI.callPluginMethod("set_per_game", { enabled: checked });
                            // Reload info to sync with the switch between global/per-game
                            await initState();
                        }}
                    />
                </PanelSectionRow>

                {perGame && (
                    <PanelSectionRow>
                        <div style={{ display: "flex", flexDirection: "row", alignItems: "center", justifyContent: "center" }}>
                            <div style={{ fontWeight: "bold" }}>{currentGameName}</div>
                        </div>
                    </PanelSectionRow>
                )}
            </PanelSection>

            <PanelSection title="Shader">
                <PanelSectionRow>
                    <ToggleField
                        label="Enable Shaders"
                        checked={shadersEnabled}
                        onChange={async (enabled: boolean) => {
                            setShadersEnabled(enabled);
                            await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                            await serverAPI.callPluginMethod("toggle_shader", {
                                shader_name: enabled ? selectedShader.data : "None"
                            });
                        }}
                    />
                </PanelSectionRow>
                <PanelSectionRow>
                    <Dropdown
                        menuLabel="Select shader"
                        strDefaultLabel={selectedShader.label as string}
                        rgOptions={shaderOptions}
                        selectedOption={selectedShader}
                        onChange={async (newSelectedShader: DropdownOption) => {
                            setSelectedShader(newSelectedShader);
                            await serverAPI.callPluginMethod("set_shader", { shader_name: newSelectedShader.data });
                            await fetchShaderParams();
                        }}
                    />
                </PanelSectionRow>
            </PanelSection>

            {hasParams && (
                <PanelSection title="Parameters">
                    {shaderParams.map(p => renderParam(p))}
                    <PanelSectionRow>
                        <ButtonItem
                            disabled={!shadersEnabled || selectedShader.data === "None"}
                            onClick={async () => {
                                await serverAPI.callPluginMethod("reset_shader_params", {});
                                await fetchShaderParams();
                                await applyShader();
                            }}
                        >Reset to Defaults</ButtonItem>
                    </PanelSectionRow>
                </PanelSection>
            )}

            <PanelSection title="Misc">
                <PanelSectionRow>
                    <ButtonItem
                        disabled={applyDisabled || !shadersEnabled || selectedShader.data === "None"}
                        onClick={async () => {
                            setApplyDisabled(true);
                            setTimeout(() => setApplyDisabled(false), 1000);
                            await applyShader();
                        }}
                    >Force Apply</ButtonItem>
                </PanelSectionRow>
            </PanelSection>

            <PanelSection title="Information">
                <PanelSectionRow>
                    <div>Place any custom shaders in <pre>~/.local/share/gamescope</pre><pre>/reshade/Shaders</pre> so that the .fx files are in the root of the Shaders folder.</div>
                </PanelSectionRow>
                <PanelSectionRow>
                    <div>WARNING: Shaders can lead to dropped frames and possibly even severe performance problems.</div>
                </PanelSectionRow>
            </PanelSection>
        </div>
    );
};

export default definePlugin((serverApi: ServerAPI) => {
    let unregisterMonitor: (() => void) | undefined;

    const checkGame = async () => {
        try {
            const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
            const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
            await serverApi.callPluginMethod("set_current_game_info", { appid, appname });
        } catch (e) {
            console.error("Reshadeck checkGame error", e);
        }
    };

    // Use SteamClient events to detect game launch/close in the background
    if (window.SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications) {
        const sub = window.SteamClient.GameSessions.RegisterForAppLifetimeNotifications((update: any) => {
            // Detect game launch -> trigger shader application immediately
            if (update.bCreated) {
                const appid = update.unAppID.toString();
                let appname = "Loading...";
                // Best effort to get name if Router is already updated
                if (Router.MainRunningApp && String(Router.MainRunningApp.appid) === appid) {
                    appname = Router.MainRunningApp.display_name;
                }
                serverApi.callPluginMethod("set_current_game_info", { appid, appname });
            }

            // Wait slightly for Router to update its state (for game close or accurate name)
            // 250ms: fast check for quick transitions
            // 500ms: standard check
            // 1500ms: backup check
            setTimeout(checkGame, 250);
            setTimeout(checkGame, 500);
            setTimeout(checkGame, 1500);
        });
        unregisterMonitor = () => {
            if (sub?.unregister) sub.unregister();
        };
    } else {
        // Fallback polling if SteamClient/Events are missing
        const i = setInterval(checkGame, 2000);
        unregisterMonitor = () => clearInterval(i);
    }

    // Initial check
    checkGame();

    return {
        title: <div className={staticClasses.Title}>Reshadeck+</div>,
        content: <Content serverAPI={serverApi} />,
        icon: <RiTvLine />,
        onDismount() {
            if (unregisterMonitor) unregisterMonitor();
        },
    };
});
