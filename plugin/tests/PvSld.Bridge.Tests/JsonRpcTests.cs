using System.Text;
using System.Text.Json.Nodes;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

public class JsonRpcTests
{
    private static JsonRpcRequest Parse(string json) => JsonRpc.Parse(Encoding.UTF8.GetBytes(json));

    [Fact]
    public void Parse_ValidRequest_ReturnsIdMethodAndParams()
    {
        var request = Parse("""{"jsonrpc":"2.0","id":7,"method":"ping","params":{"main_thread":true}}""");

        Assert.Equal(7, request.Id.GetValue<int>());
        Assert.Equal("ping", request.Method);
        Assert.True(request.Params!["main_thread"]!.GetValue<bool>());
    }

    [Fact]
    public void Parse_StringIdAndNoParams_IsAccepted()
    {
        var request = Parse("""{"jsonrpc":"2.0","id":"a-1","method":"drawing_stats"}""");

        Assert.Equal("a-1", request.Id.GetValue<string>());
        Assert.Null(request.Params);
    }

    [Theory]
    [InlineData("not json", BridgeErrorCodes.ParseError)]
    [InlineData("[1,2]", BridgeErrorCodes.InvalidRequest)]
    [InlineData("""{"id":1,"method":"ping"}""", BridgeErrorCodes.InvalidRequest)]
    [InlineData("""{"jsonrpc":"2.0","method":"ping"}""", BridgeErrorCodes.InvalidRequest)]
    [InlineData("""{"jsonrpc":"2.0","id":null,"method":"ping"}""", BridgeErrorCodes.InvalidRequest)]
    [InlineData("""{"jsonrpc":"2.0","id":1,"method":5}""", BridgeErrorCodes.InvalidRequest)]
    [InlineData("""{"jsonrpc":"2.0","id":1,"method":"ping","params":[1]}""", BridgeErrorCodes.InvalidRequest)]
    public void Parse_Malformed_ThrowsWithJsonRpcCode(string json, int code)
    {
        var error = Assert.Throws<BridgeException>(() => Parse(json));

        Assert.Equal(code, error.Code);
    }

    [Fact]
    public void Result_IsOneJsonObjectWithIdAndResult()
    {
        var line = JsonRpc.Result(JsonValue.Create(3), new JsonObject { ["pong"] = true });

        var message = JsonNode.Parse(line)!.AsObject();
        Assert.DoesNotContain('\n', line);
        Assert.Equal("2.0", message["jsonrpc"]!.GetValue<string>());
        Assert.Equal(3, message["id"]!.GetValue<int>());
        Assert.True(message["result"]!["pong"]!.GetValue<bool>());
    }

    [Fact]
    public void Error_CarriesCodeMessageAndData()
    {
        var busy = new BusyException(BusyReasons.ModalDialog, "close the dialog");

        var line = JsonRpc.Error(JsonValue.Create("x"), busy.Code, busy.Message, busy.Data);

        var error = JsonNode.Parse(line)!["error"]!;
        Assert.Equal(BridgeErrorCodes.Busy, error["code"]!.GetValue<int>());
        Assert.Equal("close the dialog", error["message"]!.GetValue<string>());
        Assert.Equal("modal_dialog", error["data"]!["reason"]!.GetValue<string>());
    }

    [Fact]
    public void TryGetId_RecoversIdFromInvalidRequest()
    {
        var id = JsonRpc.TryGetId(Encoding.UTF8.GetBytes("""{"id":42,"method":7}"""));

        Assert.Equal(42, id!.GetValue<int>());
        Assert.Null(JsonRpc.TryGetId("garbage"u8));
    }
}
