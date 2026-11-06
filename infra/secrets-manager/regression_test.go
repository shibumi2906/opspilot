package jose

import (
 "crypto/rand"
 "crypto/rsa"
 "encoding/base64"
 "encoding/json"
 "strings"
 "testing"
)

func TestF17OversizedRSAParametersRejectedBeforeArithmetic(t *testing.T) {
 for _, field := range []string{"n", "d", "p", "q", "dp", "dq", "qi", "e"} {
  t.Run(field, func(t *testing.T) {
   size := 513
   if field == "e" { size = 5 }
   oversized := base64.RawURLEncoding.EncodeToString([]byte(strings.Repeat("x", size)))
   value := map[string]string{"kty":"RSA", "n":"AQ", "e":"Aw", "d":"AQ", "p":"AQ", "q":"AQ"}
   value[field] = oversized
   data, err := json.Marshal(value)
   if err != nil { t.Fatal(err) }
   var key JSONWebKey
   err = json.Unmarshal(data, &key)
   if err == nil || !strings.Contains(err.Error(), "exceed") { t.Fatalf("operand not bounded: %v", err) }
  })
 }
 // Public parsing must enforce the modulus bound, too.
 data, _ := json.Marshal(map[string]string{"kty":"RSA", "n":base64.RawURLEncoding.EncodeToString([]byte(strings.Repeat("x", 513))), "e":"Aw"})
 var key JSONWebKey
 if err := json.Unmarshal(data, &key); err == nil || !strings.Contains(err.Error(), "exceed") { t.Fatalf("public modulus not bounded: %v", err) }
}

func TestF17ValidRSAStillRoundTrips(t *testing.T) {
 for _, bits := range []int{2048, 3072, 4096} {
  key, err := rsa.GenerateKey(rand.Reader, bits)
  if err != nil { t.Fatal(err) }
  data, err := json.Marshal(JSONWebKey{Key:key})
  if err != nil { t.Fatal(err) }
  var decoded JSONWebKey
  if err := json.Unmarshal(data, &decoded); err != nil { t.Fatalf("valid RSA%d rejected: %v", bits, err) }
 }
}
