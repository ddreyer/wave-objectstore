import wave_dht as wdht
import grpc
import base64
import wave3 as wv

class Client:
    def __init__(self):
        channel = grpc.insecure_channel("localhost:410")
        self.agent = wv.WAVEStub(channel)
        self.ent = self.agent.CreateEntity(wv.CreateEntityParams())
        self.agent.PublishEntity(wv.PublishEntityParams(DER=self.ent.PublicDER))
        self.perspective = wv.Perspective(
            entitySecret=wv.EntitySecret(DER=self.ent.SecretDER)
        )
        self.wdht_handle = wdht.WaveDht()


    def put(self, key, value, namespace):
        encrypted = self.agent.EncryptMessage(
            wv.EncryptMessageParams(
                namespace=namespace,
                resource=key,
                content=value))

        if encrypted.error.code != 0:
            raise Exception(encrypted.error.message)

        print("in client put")

        # if we are trying to put on a resource in our namespace, sign
        # key contains modified entity hash of namespace that the object is under
        if (key.split("/")[0]) == str(hash(self.ent.hash)):
            print("client is signing")
            sig = self.agent.Sign(wv.SignParams(
                perspective=self.perspective,
                content=encrypted.ciphertext
            ))
            if sig.error.code != 0:
                raise Exception(sig.error.message)

            print("key is: ", key)
            self.wdht_handle.put(key, encrypted.ciphertext, sig.signature, False, namespace)
        else:
            print("client is building proof")
            
            proof = self.agent.BuildRTreeProof(wv.BuildRTreeProofParams(
                perspective=self.perspective,
                namespace=namespace,
                resyncFirst=True,
                statements=[
                    wv.RTreePolicyStatement(
                        permissionSet=namespace,
                        permissions=["write"],
                        resource=key,
                    )
                ]
            ))
            if proof.error.code != 0:
                raise Exception(proof.error.message)

            print("key is: ", key)
            self.wdht_handle.put(key, encrypted.ciphertext, proof.proofDER, True, namespace)



    # for now, just fetch the data that is protected with E2EE
    def get(self, key):
        # proof = self.agent.BuildRTreeProof(wv.BuildRTreeProofParams(
        #     perspective=self.perspective,
        #     namespace=namespace.ent.hash,
        #     statements=[
        #         wv.RTreePolicyStatement(
        #             permissionSet=wv.WaveBuiltinPSET,
        #             permissions=[wv.WaveBuiltinE2EE],
        #             resource=key,
        #         )
        #     ]
        # ))
        results = self.wdht_handle.get(key)
        # self.agent.ResyncPerspectiveGraph(wv.ResyncPerspectiveGraphParams(
        #     perspective=self.perspective,
        # ))
        for r in results:
            resp = self.agent.DecryptMessage(wv.DecryptMessageParams(
                perspective= self.perspective,
                ciphertext= r.data,
                resyncFirst=True))
            if resp.error.code == 0:
                return resp.content
        raise Exception("could not decrypt results")
    
    def set(self, key, subj, perms=None):
        print("in set, creating attestation")
        print("resource: ", key)
        att = self.agent.CreateAttestation(wv.CreateAttestationParams(
            perspective=self.perspective,
            subjectHash=subj,
            publish=True,
            policy=wv.Policy(rTreePolicy=wv.RTreePolicy(
                namespace=self.ent.hash,
                indirections=5,
                statements=[
                    wv.RTreePolicyStatement(
                        # This is a permission set used for special permissions
                        permissionSet=wv.WaveBuiltinPSET,
                        # this special permission generates end-to-end decryption keys
                        permissions=[wv.WaveBuiltinE2EE],
                        resource=key,
                    )]
            ))))
        if att.error.code != 0:
            raise Exception(att.error.message)
        if perms:
            att = self.agent.CreateAttestation(wv.CreateAttestationParams(
                perspective=self.perspective,
                subjectHash=subj,
                publish=True,
                policy=wv.Policy(rTreePolicy=wv.RTreePolicy(
                    namespace=self.ent.hash,
                    indirections=5,
                    statements=[
                        wv.RTreePolicyStatement(
                            # This is a permission set used for special permissions
                            permissionSet=self.ent.hash,
                            # this special permission generates end-to-end decryption keys
                            permissions=perms,
                            resource=key,
                        )]
                ))))
            if att.error.code != 0:
                raise Exception(att.error.message)
