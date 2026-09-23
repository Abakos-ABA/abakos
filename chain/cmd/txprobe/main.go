package main

// txprobe: decodes a captured TxRaw and tests the EIP-191 (personal_sign) digest and the
// amino sign doc WITHOUT the dropNulls normalisation (legacytx.StdSignBytes).

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"

	txv1beta1 "cosmossdk.io/api/cosmos/tx/v1beta1"
	sdkmath "cosmossdk.io/math"
	txsigning "cosmossdk.io/x/tx/signing"
	"google.golang.org/protobuf/proto"

	"github.com/cosmos/cosmos-sdk/codec/legacy"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/x/auth/migrations/legacytx"
	"github.com/cosmos/evm/crypto/ethsecp256k1"
	"github.com/cosmos/evm/ethereum/eip712"
	gethcrypto "github.com/ethereum/go-ethereum/crypto"

	"pkg.akt.dev/go/sdkutil"
	"pkg.akt.dev/node/v2/app"
	apptypes "pkg.akt.dev/node/v2/app/types"
)

func init() {
	defer func() { _ = recover() }()
	sdk.GetConfig().SetBech32PrefixForAccount("abakos", "abakospub")
}

func queryAccountNumber(addr string) uint64 {
	resp, err := http.Get("http://localhost:1317/cosmos/auth/v1beta1/accounts/" + addr)
	if err != nil {
		return 0
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	var jr struct {
		Account struct {
			AccountNumber string `json:"account_number"`
		} `json:"account"`
	}
	if json.Unmarshal(b, &jr) != nil {
		return 0
	}
	var n uint64
	fmt.Sscanf(jr.Account.AccountNumber, "%d", &n)
	return n
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func extractKey(v []byte) []byte {
	if len(v) >= 2 && v[0] == 0x0a {
		l := int(v[1])
		if len(v) >= 2+l {
			return v[2 : 2+l]
		}
	}
	return v
}

func eip191(msg []byte) []byte {
	return gethcrypto.Keccak256(append([]byte(fmt.Sprintf("\x19Ethereum Signed Message:\n%d", len(msg))), msg...))
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: txprobe2 <base64-txraw> [accountNumber]")
		os.Exit(1)
	}
	txBytes, err := base64.StdEncoding.DecodeString(os.Args[1])
	must(err)
	acctNum := uint64(0)
	if len(os.Args) >= 3 {
		fmt.Sscanf(os.Args[2], "%d", &acctNum)
	}

	ec := sdkutil.MakeEncodingConfig()
	app.ModuleBasics().RegisterLegacyAminoCodec(ec.Amino)
	app.ModuleBasics().RegisterInterfaces(ec.InterfaceRegistry)
	app.RegisterEVMCryptoInterfaces(ec.InterfaceRegistry)
	eip712.RegisterInterfaces(ec.InterfaceRegistry)
	eip712.SetEncodingConfig(ec.Amino, ec.InterfaceRegistry, apptypes.AbakosEVMChainID)
	ec.Amino.RegisterConcrete(&ethsecp256k1.PubKey{}, ethsecp256k1.PubKeyName, nil)
	ec.Amino.RegisterConcrete(&ethsecp256k1.PrivKey{}, ethsecp256k1.PrivKeyName, nil)
	legacy.Cdc.RegisterConcrete(&ethsecp256k1.PubKey{}, ethsecp256k1.PubKeyName, nil)
	legacy.Cdc.RegisterConcrete(&ethsecp256k1.PrivKey{}, ethsecp256k1.PrivKeyName, nil)
	legacytx.RegressionTestingAminoCodec = ec.Amino

	var raw txv1beta1.TxRaw
	must(proto.Unmarshal(txBytes, &raw))
	var body txv1beta1.TxBody
	must(proto.Unmarshal(raw.BodyBytes, &body))
	var authInfo txv1beta1.AuthInfo
	must(proto.Unmarshal(raw.AuthInfoBytes, &authInfo))

	si := authInfo.SignerInfos[0]
	seq := si.Sequence
	sig := raw.Signatures[0]
	pk := ethsecp256k1.PubKey{Key: extractKey(si.PublicKey.Value)}

	ethPub, err := gethcrypto.DecompressPubkey(pk.Key)
	must(err)
	eAddr := gethcrypto.PubkeyToAddress(*ethPub)
	expected := fmt.Sprintf("0x%x", eAddr)
	abakosAddr := sdk.AccAddress(eAddr.Bytes()).String()
	if acctNum == 0 {
		acctNum = queryAccountNumber(abakosAddr)
	}
	fmt.Printf("msgs: ")
	for _, m := range body.Messages {
		fmt.Printf("%s ", m.TypeUrl)
	}
	fmt.Printf("\nmemo=%q mode=%v seq=%d sigLen=%d v=%d\nsigner: %s (%s) account_number=%d\n", body.Memo, si.ModeInfo, seq, len(sig), sig[len(sig)-1], abakosAddr, expected, acctNum)

	handler := sdkutil.NewLegacyAminoJSONHandler(ec.Amino, ec.InterfaceRegistry)
	amino, err := handler.GetSignBytes(context.Background(),
		txsigning.SignerData{ChainID: "abakos-sandbox-1", AccountNumber: acctNum, Sequence: seq},
		txsigning.TxData{Body: &body, AuthInfo: &authInfo})
	must(err)
	fmt.Printf("\n=== node amino sign doc (current handler, dropNulls) ===\n%s\n", string(amino))

	// Raw amino without dropNulls, via legacytx.StdSignBytes
	msgs := make([]sdk.Msg, len(body.Messages))
	for i, a := range body.Messages {
		var m sdk.Msg
		must(ec.InterfaceRegistry.UnpackAny(&codectypes.Any{TypeUrl: a.TypeUrl, Value: a.Value}, &m))
		msgs[i] = m
	}
	fee := legacytx.StdFee{Gas: authInfo.Fee.GasLimit}
	for _, c := range authInfo.Fee.Amount {
		n, _ := sdkmath.NewIntFromString(c.Amount)
		fee.Amount = append(fee.Amount, sdk.Coin{Denom: c.Denom, Amount: n})
	}
	rawAmino := legacytx.StdSignBytes("abakos-sandbox-1", acctNum, seq, body.TimeoutHeight, fee, msgs, body.Memo)
	fmt.Printf("\n=== raw amino sign doc (no dropNulls) ===\n%s\n", string(rawAmino))

	sd := &txv1beta1.SignDoc{BodyBytes: raw.BodyBytes, AuthInfoBytes: raw.AuthInfoBytes, ChainId: "abakos-sandbox-1", AccountNumber: acctNum}
	directBytes, err := proto.Marshal(sd)
	must(err)

	fmt.Printf("\n=== node verdict ===\npk.VerifySignature(amino) = %v\npk.VerifySignature(rawAmino) = %v\npk.VerifySignature(direct) = %v\n",
		pk.VerifySignature(amino, sig), pk.VerifySignature(rawAmino, sig), pk.VerifySignature(directBytes, sig))

	sig64 := sig
	if len(sig64) == 65 {
		sig64 = sig64[:64]
	}
	type cand struct {
		name string
		hash []byte
	}
	cands := []cand{
		{"keccak(direct)", gethcrypto.Keccak256(directBytes)},
		{"keccak(amino)", gethcrypto.Keccak256(amino)},
		{"keccak(rawAmino)", gethcrypto.Keccak256(rawAmino)},
		{"eip191(amino)", eip191(amino)},
		{"eip191(rawAmino)", eip191(rawAmino)},
		{"eip191(direct)", eip191(directBytes)},
	}
	if e, err := eip712.GetEIP712BytesForMsg(amino); err == nil {
		cands = append(cands, cand{"keccak(eip712(amino))", gethcrypto.Keccak256(e)})
	} else {
		fmt.Println("eip712(amino) err:", err)
	}
	if e, err := eip712.GetEIP712BytesForMsg(rawAmino); err == nil {
		cands = append(cands, cand{"keccak(eip712(rawAmino))", gethcrypto.Keccak256(e)})
	} else {
		fmt.Println("eip712(rawAmino) err:", err)
	}
	if e, err := eip712.LegacyGetEIP712BytesForMsg(amino); err == nil {
		cands = append(cands, cand{"keccak(legacy712(amino))", gethcrypto.Keccak256(e)})
	} else {
		fmt.Println("legacy712(amino) err:", err)
	}
	fmt.Printf("\n=== ecrecover ===\n")
	for _, c := range cands {
		for v := byte(0); v <= 1; v++ {
			s65 := append(append([]byte{}, sig64...), v)
			rec, err := gethcrypto.SigToPub(c.hash, s65)
			if err != nil {
				continue
			}
			addr := fmt.Sprintf("0x%x", gethcrypto.PubkeyToAddress(*rec))
			match := ""
			if addr == expected {
				match = "  <<< MATCH"
			}
			fmt.Printf("  %-26s v=%d -> %s%s\n", c.name, v, addr, match)
		}
	}
}
