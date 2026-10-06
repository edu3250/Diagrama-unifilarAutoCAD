using System.Text.Json.Nodes;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

public class BridgeParamsTests
{
    private static JsonObject P(string json) => JsonNode.Parse(json)!.AsObject();

    [Fact]
    public void RequirePoint_Accepts2dAnd3d()
    {
        Assert.Equal((1.5, 2, 0), BridgeParams.RequirePoint(P("""{"p":[1.5,2]}""")["p"], "p"));
        Assert.Equal((1, 2, 3), BridgeParams.RequirePoint(P("""{"p":[1,2,3]}""")["p"], "p"));
    }

    [Theory]
    [InlineData("""{"p":[1]}""")]
    [InlineData("""{"p":[1,2,3,4]}""")]
    [InlineData("""{"p":["1",2]}""")]
    [InlineData("""{"p":"1,2"}""")]
    [InlineData("""{}""")]
    public void RequirePoint_Rejects(string json)
    {
        var error = Assert.Throws<BridgeException>(() => BridgeParams.RequirePoint(P(json)["p"], "p"));

        Assert.Equal(BridgeErrorCodes.InvalidParams, error.Code);
    }

    [Fact]
    public void StringMap_IsCaseInsensitiveAndRejectsNonStrings()
    {
        var map = BridgeParams.StringMap(P("""{"a":{"comp_id":"PV-1"}}""")["a"], "a");

        Assert.Equal("PV-1", map["COMP_ID"]);
        Assert.Throws<BridgeException>(() => BridgeParams.StringMap(P("""{"a":{"x":1}}""")["a"], "a"));
    }

    [Fact]
    public void OptionalInt_EnforcesRange()
    {
        Assert.Null(BridgeParams.OptionalInt(P("{}"), "n"));
        Assert.Equal(3, BridgeParams.OptionalInt(P("""{"n":3}"""), "n", 0, 10));
        Assert.Throws<BridgeException>(() => BridgeParams.OptionalInt(P("""{"n":-1}"""), "n", 0, 10));
        Assert.Throws<BridgeException>(() => BridgeParams.OptionalInt(P("""{"n":1.5}"""), "n"));
    }

    [Fact]
    public void RequireString_EnforcesTypeAndLength()
    {
        Assert.Equal("ok", BridgeParams.RequireString(P("""{"s":"ok"}"""), "s"));
        Assert.Throws<BridgeException>(() => BridgeParams.RequireString(P("{}"), "s"));
        Assert.Throws<BridgeException>(() => BridgeParams.RequireString(P("""{"s":5}"""), "s"));
        Assert.Throws<BridgeException>(() => BridgeParams.RequireString(P("""{"s":"toolong"}"""), "s", maxLength: 3));
    }
}
