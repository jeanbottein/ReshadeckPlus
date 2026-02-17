uniform float Contrast   = 0.000000;
uniform float Sharpness  = 1.000000;

// "Contrast Adaptation", Adjusts the range the shader adapts to high contrast (0 is not all the way off).  Higher values = more high contrast sharpening.
// "Sharpening intensity", Adjusts sharpening intensity by averaging the original pixels to the sharpened result.  1.0 is the unmodified default.

// Required dummy timer uniform
uniform float iGlobalTime < source = "timer"; >;

#include "ReShade.fxh"
static const float2 pixel = float2(BUFFER_RCP_WIDTH, BUFFER_RCP_HEIGHT);

void CASPass(float4 pos : SV_Position, float2 texcoord : TexCoord, out float3 color : SV_Target)
{
	// Sample 3x3 neighborhood
	float3 a = tex2D(ReShade::BackBuffer, texcoord + pixel * float2(-1, -1)).rgb;
	float3 b = tex2D(ReShade::BackBuffer, texcoord + pixel * float2( 0, -1)).rgb;
	float3 c = tex2D(ReShade::BackBuffer, texcoord + pixel * float2( 1, -1)).rgb;
	float3 d = tex2D(ReShade::BackBuffer, texcoord + pixel * float2(-1,  0)).rgb;
	float3 e = tex2D(ReShade::BackBuffer, texcoord).rgb;
	float3 f = tex2D(ReShade::BackBuffer, texcoord + pixel * float2( 1,  0)).rgb;
	float3 g = tex2D(ReShade::BackBuffer, texcoord + pixel * float2(-1,  1)).rgb;
	float3 h = tex2D(ReShade::BackBuffer, texcoord + pixel * float2( 0,  1)).rgb;
	float3 i = tex2D(ReShade::BackBuffer, texcoord + pixel * float2( 1,  1)).rgb;

	// Compute local min and max (for adaptive behavior)
	float3 mnRGB = min(min(min(d, e), min(f, b)), h);
	float3 mnRGB2 = min(mnRGB, min(min(a, c), min(g, i)));
	mnRGB += mnRGB2;

	float3 mxRGB = max(max(max(d, e), max(f, b)), h);
	float3 mxRGB2 = max(mxRGB, max(max(a, c), max(g, i)));
	mxRGB += mxRGB2;

	// Smooth minimum distance to signal limit divided by smooth max.
	float3 ampRGB = saturate(min(mnRGB, 2.0 - mxRGB) * rcp(mxRGB));

	// Shaping amount of sharpening.
	ampRGB = rsqrt(ampRGB);

	float peak = -3.0 * Contrast + 8.0;
	float3 wRGB = -rcp(ampRGB * peak);

	float3 rcpWeightRGB = rcp(4.0 * wRGB + 1.0);

	// Box blur neighborhood
	float3 window = b + d + f + h;

	// Apply adaptive sharpening
	float3 sharpened = saturate((window * wRGB + e) * rcpWeightRGB);

	// Mix original and sharpened based on strength
	color = lerp(e, sharpened, Sharpness);
}

technique ContrastAdaptiveSharpen10
{
	pass
	{
		VertexShader = PostProcessVS;
		PixelShader = CASPass;
	}
}
