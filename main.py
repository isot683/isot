
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import SaveDraftRequest
from telethon.tl.functions.users import GetFullUserRequest
from datetime import datetime, timezone

class TelegramMultiDraftSender:
    def __init__(self):
        self.api_id = 25680079 
        self.api_hash = '055d344ca63570ab232917a8292bba80'
        
        self.phones = [
            {'number': '+905535350731', 'group': 'https://t.me/busralgotrade'},
            {'number': '+905494817128', 'group': 'https://t.me/ozdemirhocaborsa'},
            {'number': '+905482160208', 'group': 'https://t.me/TeknikkBorsa'},
        ]
        
        self.draft_message = "."
        
        self.target_user_count = 45
    
        # Yeni özellik: Tepki süresi kontrolü
        self.check_reaction_time = True  # Bu özelliği açmak için True yapın
        
        self.clients = {}
    
    async def create_clients(self):
        """Tüm hesaplar için client oluştur"""
        for phone_data in self.phones:
            phone = phone_data['number']
            session_name = f"session_{phone.replace('+', '').replace(' ', '')}"
            
            client = TelegramClient(session_name, self.api_id, self.api_hash)
            await client.start(phone=phone)
            
            self.clients[phone] = client
            print(f"Client oluşturuldu: {phone}")
    
    async def get_group_entity(self, client, group_url):
        """Grup URL'sinden grup entity'sini al"""
        try:
            if 't.me/' in group_url:
                username = group_url.split('t.me/')[-1]
                entity = await client.get_entity(username)
                return entity
        except Exception as e:
            print(f"Grup entity alınamadı: {e}")
            return None
    
    async def get_user_online_status(self, client, user_id):
        """Kullanıcının son çevrimiçi durumunu al"""
        try:
            full_user = await client(GetFullUserRequest(user_id))
            user_status = full_user.users[0].status
            
            if hasattr(user_status, 'was_online'):
                return user_status.was_online
            elif hasattr(user_status, 'expires'):
                return user_status.expires
            else:
                return None
                
        except Exception as e:
            print(f"Kullanıcı durumu alınamadı {user_id}: {e}")
            return None
    
    async def should_send_to_user(self, client, user, message_date):
        """Kullanıcıya mesaj gönderilip gönderilmeyeceğini kontrol et"""
        if not self.check_reaction_time:
            return True
        
        try:
            last_online = await self.get_user_online_status(client, user.id)
            
            if last_online is None:
                print(f"Kullanıcı {user.id} durumu alınamadı, gönderiliyor")
                return True
            
            # Timezone aware datetime'ları karşılaştır
            if message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)
            if last_online.tzinfo is None:
                last_online = last_online.replace(tzinfo=timezone.utc)
            
            # Eğer tepki süresi ile son çevrimiçi olma süresi aynı veya çok yakınsa (5 dakika tolerans)
            time_diff = abs((message_date - last_online).total_seconds())
            
            if time_diff <= 60:  # 1 dakika tolerans
                print(f"Kullanıcı {user.id} tepki süresi ile çevrimiçi süresi aynı, atlanıyor")
                return False
            
            return True
            
        except Exception as e:
            print(f"Kullanıcı kontrolü hatası {user.id}: {e}")
            return True  # Hata durumunda gönder
    
    async def get_reaction_users_until_target(self, client, group_entity, target_count=45):
        """Hedef sayıya ulaşana kadar geriye doğru mesajları tara"""
        try:
            unique_users = set()
            processed_users = []
            offset_id = 0
            
            print(f"Hedef kullanıcı sayısı: {target_count}")
            
            while len(unique_users) < target_count:
                messages = await client.get_messages(
                    group_entity, 
                    limit=100,
                    offset_id=offset_id
                )
                
                if not messages:
                    print("Daha fazla mesaj bulunamadı")
                    break
                
                for message in messages:
                    if message.reactions and message.reactions.results:
                        print(f"Tepkili mesaj: {message.id} - Tepki sayısı: {sum(r.count for r in message.reactions.results)}")
                        
                        for reaction in message.reactions.results:
                            try:
                                from telethon.tl.functions.messages import GetMessageReactionsListRequest
                                
                                reaction_users = await client(GetMessageReactionsListRequest(
                                    peer=group_entity,
                                    id=message.id,
                                    reaction=reaction.reaction,
                                    limit=min(reaction.count, 100)
                                ))
                                
                                for user in reaction_users.users:
                                    if user.id not in unique_users:
                                        # Kullanıcıya gönderilip gönderilmeyeceğini kontrol et
                                        if await self.should_send_to_user(client, user, message.date):
                                            unique_users.add(user.id)
                                            processed_users.append(user)
                                            
                                            print(f"Yeni kullanıcı eklendi: {user.id} (Toplam: {len(unique_users)})")
                                            
                                            if len(unique_users) >= target_count:
                                                print(f"Hedef sayıya ulaşıldı: {len(unique_users)}")
                                                return processed_users[:target_count]
                                        else:
                                            print(f"Kullanıcı {user.id} kriterleri karşılamıyor, atlandı")
                                
                                await asyncio.sleep(0.5)
                                
                            except Exception as reaction_error:
                                continue

                    offset_id = message.id
                
                await asyncio.sleep(1)
                print(f"İşlenen kullanıcı: {len(unique_users)}")
            
            print(f"Toplam {len(processed_users)} benzersiz kullanıcı bulundu")
            return processed_users
            
        except Exception as e:
            print(f"Hata: {e}")
            return []
    
    async def send_saved_draft(self, client, user_id, message_text):
        """Kullanıcıya saved draft gönder"""
        try:
            await client(SaveDraftRequest(
                peer=user_id,
                message=message_text,
                entities=[],
                reply_to=None,
                no_webpage=False
            ))
            
            print(f"Draft gönderildi: {user_id}")
            return True
            
        except Exception as e:
            print(f"Draft hatası {user_id}: {e}")
            return False
    
    async def process_account(self, phone_data):
        """Bir hesap için tüm işlemleri gerçekleştir"""
        phone = phone_data['number']
        group_url = phone_data['group']
        
        try:
            client = self.clients[phone]
            print(f"İşlem başlatılıyor: {phone} -> {group_url}")
            
            group_entity = await self.get_group_entity(client, group_url)
            if not group_entity:
                print(f"Grup bulunamadı: {group_url}")
                return
            
            users_with_reactions = await self.get_reaction_users_until_target(
                client, 
                group_entity, 
                self.target_user_count
            )
            
            if not users_with_reactions:
                print(f"Yeterli tepki veren kullanıcı bulunamadı: {group_url}")
                return
            
            success_count = 0
            total_users = len(users_with_reactions)
            
            print(f"Toplam {total_users} kullanıcıya draft gönderiliyor...")
            
            for i, user in enumerate(users_with_reactions, 1):
                try:
                    if await self.send_saved_draft(client, user.id, self.draft_message):
                        success_count += 1
                    
                    if i % 10 == 0 or i == total_users:
                        print(f"İlerleme: {i}/{total_users} - Başarılı: {success_count}")
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as user_error:
                    continue
            
            print(f"Hesap {phone} tamamlandı: {success_count}/{total_users} başarılı")
            
        except Exception as e:
            print(f"Hesap hatası {phone}: {e}")
    
    async def run(self):
        """Ana çalıştırma fonksiyonu"""
        try:
            await self.create_clients()
            
            tasks = []
            for phone_data in self.phones:
                task = asyncio.create_task(self.process_account(phone_data))
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            
            print("Tüm işlemler tamamlandı!")
            
        except Exception as e:
            print(f"Genel hata: {e}")
        
        finally:
            for client in self.clients.values():
                await client.disconnect()

async def main():
    sender = TelegramMultiDraftSender()
    await sender.run()

if __name__ == "__main__":
    # Gerekli kütüphaneler:
    # pip install telethon
    
    print("Telegram Multi-Account Saved Draft Sender")
    print("=" * 50)
    print("Kurulum:")
    print("1. my.telegram.org'dan API ID ve Hash alın")
    print("2. Environment variable'ları ayarlayın:")
    print("   export TELEGRAM_API_ID='your_api_id'")
    print("   export TELEGRAM_API_HASH='your_api_hash'")
    print("3. phones listesini istediğiniz gibi düzenleyin")
    print("4. draft_message değişkenini istediğiniz mesajla değiştirin")
    print("5. target_user_count değerini istediğiniz sayıyla değiştirin (varsayılan: 45)")
    print("6. check_reaction_time True ise tepki süresi kontrolü yapar")
    print("=" * 50)
    
    asyncio.run(main())