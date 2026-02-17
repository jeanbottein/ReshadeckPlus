import {
    ButtonItem,
    definePlugin,
    DialogButton,
    Menu,
    MenuItem,
    PanelSection,
    PanelSectionRow,
    ToggleField,
    Router,
    ServerAPI,
    showContextMenu,
    staticClasses,
    Dropdown,
    DropdownOption,
    SingleDropdownOption,
    SliderField
} from "decky-frontend-lib";
import { VFC, useState, useEffect, useRef } from "react";
import { MdWbShade } from "react-icons/md";
import logo from "../assets/logo.png";

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
}

// ---- Display helpers ----
/** Replace underscores with spaces and strip any trailing " [ShaderName]" bracket from labels */
const formatDisplayName = (name: string): string =>
    name.replace(/\.fx$/i, "").replace(/_/g, " ").replace(/\s*\[.*?\]\s*$/, "").trim();

// Global refresh function reference
let forceRefreshContent: (() => void) | null = null;

class ReshadeckLogic {
    serverAPI: ServerAPI;
    dataTakenAt: number = Date.now();

    constructor(serverAPI: ServerAPI) {
        this.serverAPI = serverAPI;
    }

    handleSuspend = async () => {
        // Do nothing or log if you want
    };

    handleResume = async () => {
        //		await this.serverAPI.callPluginMethod("apply_shader", {});
    };
}

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
    const baseShader = { data: "None", label: "No Shader" } as SingleDropdownOption;
    const [shadersEnabled, setShadersEnabled] = useState<boolean>(false);
    const [shader_list, set_shader_list] = useState<string[]>([]);
    const [selectedShader, setSelectedShader] = useState<DropdownOption>(baseShader);
    const [shaderOptions, setShaderOptions] = useState<DropdownOption[]>([baseShader]);
    const [currentGameId, setCurrentGameId] = useState<string>("Unknown");
    const [currentGameName, setCurrentGameName] = useState<string>("Unknown");
    const [currentEffect, setCurrentEffect] = useState<string>("");
    const [shaderParams, setShaderParams] = useState<ShaderParam[]>([]);
    const paramTimeouts = useRef<{ [key: string]: number }>({});
    const [applyDisabled, setApplyDisabled] = useState(false);

    // --- Add refreshVersion state for UI refreshes ---
    const [refreshVersion, setRefreshVersion] = useState(0);
    forceRefreshContent = () => setRefreshVersion(v => v + 1);

    const getShaderOptions = (le_list: string[], baseShaderOrSS: any) => {
        let options: DropdownOption[] = [];
        options.push(baseShaderOrSS);
        for (let i = 0; i < le_list.length; i++) {
            let option = { data: le_list[i], label: formatDisplayName(le_list[i]) } as SingleDropdownOption;
            options.push(option);
        }
        return options;
    }

    const fetchShaderParams = async () => {
        const resp = await serverAPI.callPluginMethod("get_shader_params", {});
        if (resp.result && Array.isArray(resp.result)) {
            setShaderParams(resp.result as ShaderParam[]);
        } else {
            setShaderParams([]);
        }
    };

    const refreshCurrentGameInfo = async () => {
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
        setCurrentGameId(appid);
        setCurrentGameName(appname);

        await serverAPI.callPluginMethod("set_current_game_info", {
            appid,
            appname
        });
    };

    const initState = async () => {
        await refreshCurrentGameInfo();

        let shader_list = (await serverAPI.callPluginMethod("get_shader_list", {})).result as string[];
        set_shader_list(shader_list)
        setShaderOptions(getShaderOptions(shader_list, baseShader));

        let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        let isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        let curr = await serverAPI.callPluginMethod("get_current_shader", {});
        setSelectedShader({ data: curr.result, label: (curr.result == "0" ? "None" : formatDisplayName(curr.result as string)) } as SingleDropdownOption);

        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
        setCurrentEffect((eff.result as { effect: string }).effect || "");

        // Fetch params for current shader
        await fetchShaderParams();
    }

    // --- Init state on mount and on refreshVersion bump ---
    useEffect(() => {
        initState();
    }, [refreshVersion]);

    // --- Helper to auto-apply the shader (forces gamescope reload) ---
    const applyShader = async () => {
        await serverAPI.callPluginMethod("apply_shader", {});
        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
        setCurrentEffect((eff.result as { effect: string }).effect || "");
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
            <PanelSection title="Game">
                <PanelSectionRow>
                    <div>
                        <div><b>Current Game:</b> {currentGameName}</div>
                    </div>
                </PanelSectionRow>
            </PanelSection>

            <PanelSection title="Shader">
                <PanelSectionRow>
                    <ToggleField
                        label="Enable Shaders"
                        checked={shadersEnabled}
                        onChange={async (enabled: boolean) => {
                            setShadersEnabled(enabled);
                            await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                            if (enabled) {
                                await serverAPI.callPluginMethod("toggle_shader", { shader_name: selectedShader.data });
                            } else {
                                await serverAPI.callPluginMethod("toggle_shader", { shader_name: "None" });
                            }
                            let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                            setCurrentEffect((eff.result as { effect: string }).effect || "");
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
                            await serverAPI.callPluginMethod("set_shader", { "shader_name": newSelectedShader.data });
                            let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                            setCurrentEffect((eff.result as { effect: string }).effect || "");
                            // Fetch updated params for new shader
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
    let logic = new ReshadeckLogic(serverApi);
    //	let suspend_registers = [
    //		window.SteamClient.System.RegisterForOnSuspendRequest(logic.handleSuspend),
    //		window.SteamClient.System.RegisterForOnResumeFromSuspend(logic.handleResume),
    //	];

    let lastAppId = `${Router.MainRunningApp?.appid || "Unknown"}`;
    const interval = setInterval(async () => {
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;

        if (appid !== lastAppId) {
            lastAppId = appid;
            await serverApi.callPluginMethod("set_current_game_info", {
                appid,
                appname,
            });
            // --- Notify UI to refresh if overlay is open ---
            if (forceRefreshContent) forceRefreshContent();
        }
    }, 5000);

    return {
        title: <div className={staticClasses.Title}>Reshadeck</div>,
        content: <Content serverAPI={serverApi} />,
        icon: <MdWbShade />,
        onDismount() {
            //    suspend_registers[0].unregister();
            //    suspend_registers[1].unregister();

            clearInterval(interval);
        },
        alwaysRender: true
    };
});
