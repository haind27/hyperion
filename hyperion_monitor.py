"""
Hyperion Pool and Position Monitor Script
Fetches pool information and wallet positions from Hyperion GraphQL API
"""

import argparse
import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any

import requests
from dotenv import load_dotenv
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hyperion_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Hyperion GraphQL API endpoint
HYPERION_GRAPHQL_URL = "https://hyperfluid-api.alcove.pro/v1/graphql"


class HyperionMonitor:
    """Monitor class for fetching pool and position data from Hyperion"""
    
    def __init__(self, node_api_url: str, api_key: str):
        """
        Initialize Hyperion Monitor
        
        Args:
            node_api_url: Aptos node API URL
            api_key: Aptos API key
        """
        self.node_api_url = node_api_url
        self.api_key = api_key
        self.graphql_url = HYPERION_GRAPHQL_URL
        logger.info(f"Initialized HyperionMonitor with GraphQL endpoint: {self.graphql_url}")
    
    def _execute_graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query
        
        Args:
            query: GraphQL query string
            variables: Query variables dictionary
            
        Returns:
            Response data as dictionary
            
        Raises:
            Exception: If query execution fails
        """
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        logger.debug(f"Executing GraphQL query: {query[:200]}...")
        if variables:
            logger.debug(f"Query variables: {variables}")
        
        try:
            response = requests.post(
                self.graphql_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "errors" in result:
                error_msg = f"GraphQL errors: {result['errors']}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            logger.info("GraphQL query executed successfully")
            logger.debug(f"Response data keys: {list(result.get('data', {}).keys())}")
            
            return result.get("data", {})
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise
    
    def get_pool_by_id(self, pool_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pool information by pool ID
        
        Args:
            pool_id: Pool ID to fetch
            
        Returns:
            Pool information dictionary or None if failed
        """
        logger.info(f"Fetching pool information for pool ID: {pool_id}")
        
        query = """
        query GetPoolStat($poolId: String = "") {
            api {
                getPoolStat(poolId: $poolId) {
                    dailyVolumeUSD
                    farmAPR
                    feeAPR
                    feesUSD
                    id
                    tvlUSD
                    pool {
                        currentTick
                        activeLpAmount
                        feeRate
                        sqrtPrice
                        token1
                        token2
                    }
                }
            }
        }
        """
        
        variables = {"poolId": pool_id}
        
        try:
            data = self._execute_graphql_query(query, variables)
            pool_stat = data.get("api", {}).get("getPoolStat", [])
            
            if not pool_stat:
                logger.warning(f"No pool data found for pool ID: {pool_id}")
                return None
            
            # If poolId is provided, should return single pool or first result
            pool_info = pool_stat[0] if isinstance(pool_stat, list) else pool_stat
            
            logger.info(f"Successfully fetched pool information for pool ID: {pool_id}")
            logger.debug(f"Pool TVL: ${pool_info.get('tvlUSD', 'N/A')}")
            
            return pool_info
            
        except Exception as e:
            logger.error(f"Failed to fetch pool by ID {pool_id}: {str(e)}")
            return None
    
    def get_positions_by_address(self, wallet_address: str) -> Optional[list]:
        """
        Get all positions for a wallet address
        
        Args:
            wallet_address: Wallet address to fetch positions for
            
        Returns:
            List of positions or None if failed
        """
        logger.info(f"Fetching positions for wallet address: {wallet_address}")
        
        # GraphQL query for positions - inferred from SDK structure
        query = """
        query GetPositionsByAddress($address: String!) {
            api {
                getPositionsByAddress(address: $address) {
                    isActive
                    value
                    subsidy {
                        claimed {
                            amount
                            amountUSD
                            token
                        }
                        unclaimed {
                            amount
                            amountUSD
                            token
                        }
                    }
                    fees {
                        claimed {
                            amount
                            amountUSD
                            token
                        }
                        unclaimed {
                            amount
                            amountUSD
                            token
                        }
                    }
                    position {
                        objectId
                        poolId
                        tickLower
                        tickUpper
                        createdAt
                        pool {
                            currentTick
                            feeRate
                            feeTier
                            poolId
                            senderAddress
                            sqrtPrice
                            token1
                            token2
                            token1Info {
                                assetType
                                bridge
                                coinMarketcapId
                                coinType
                                coingeckoId
                                decimals
                                faType
                                hyperfluidSymbol
                                logoUrl
                                name
                                symbol
                                isBanned
                                websiteUrl
                            }
                            token2Info {
                                assetType
                                bridge
                                coinMarketcapId
                                coinType
                                coingeckoId
                                decimals
                                faType
                                hyperfluidSymbol
                                logoUrl
                                name
                                symbol
                                isBanned
                                websiteUrl
                            }
                        }
                    }
                }
            }
        }
        """
        
        variables = {"address": wallet_address}
        
        try:
            data = self._execute_graphql_query(query, variables)
            positions = data.get("api", {}).get("getPositionsByAddress", [])
            
            if not positions:
                logger.warning(f"No positions found for wallet address: {wallet_address}")
                return []
            
            logger.info(f"Successfully fetched {len(positions)} position(s) for wallet address: {wallet_address}")
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to fetch positions for address {wallet_address}: {str(e)}")
            # Try alternative query structure if the first one fails
            logger.info("Attempting alternative query structure...")
            return self._get_positions_alternative(wallet_address)
    
    def _get_positions_alternative(self, wallet_address: str) -> Optional[list]:
        """
        Alternative method to get positions - simpler query structure
        """
        query = """
        query GetPositions($address: String!) {
            positions(address: $address) {
                isActive
                value
                position {
                    objectId
                    poolId
                    tickLower
                    tickUpper
                }
            }
        }
        """
        
        variables = {"address": wallet_address}
        
        try:
            data = self._execute_graphql_query(query, variables)
            positions = data.get("positions", [])
            
            if positions:
                logger.info(f"Successfully fetched {len(positions)} position(s) using alternative query")
            
            return positions
            
        except Exception as e:
            logger.error(f"Alternative query also failed: {str(e)}")
            return None
    
    def save_to_json(self, data: Any, filename: str) -> bool:
        """
        Save data to JSON file
        
        Args:
            data: Data to save
            filename: Output filename
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Data saved to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save data to {filename}: {str(e)}")
            return False


async def test_aptos_connection(node_api_url: str, api_key: str):
    """
    Test Aptos node connection
    
    Args:
        node_api_url: Aptos node API URL
        api_key: Aptos API key
    """
    try:
        logger.info("Testing Aptos node connection...")
        node_api_client = RestClient(node_api_url)
        node_api_client.client.headers["Authorization"] = f"Bearer {api_key}"
        
        response = await node_api_client.account(AccountAddress.from_str("0x1"))
        logger.info("Aptos node connection successful")
        logger.debug(f"Test account response keys: {list(response.keys())}")
        
    except Exception as e:
        logger.warning(f"Aptos node connection test failed: {str(e)}")
        logger.warning("This may not affect Hyperion GraphQL API calls")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Monitor Hyperion pools and positions on Aptos network"
    )
    parser.add_argument(
        "--node-api-url",
        help="Aptos node API URL (overrides .env)",
        default=None
    )
    parser.add_argument(
        "--api-key",
        help="Aptos API key (overrides .env)",
        default=None
    )
    parser.add_argument(
        "--wallet-address",
        help="Wallet address to monitor (overrides .env)",
        default=None
    )
    parser.add_argument(
        "--pool-id",
        help="Pool ID to fetch (overrides .env)",
        default=None
    )
    parser.add_argument(
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    
    return parser.parse_args()


async def main():
    """Main function"""
    # Load environment variables
    load_dotenv()
    
    # Parse arguments
    args = parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Get configuration from args or .env
    node_api_url = args.node_api_url or os.getenv("NODE_API_URL")
    api_key = args.api_key or os.getenv("API_KEY")
    wallet_address = args.wallet_address or os.getenv("WALLET_ADDRESS")
    pool_id = args.pool_id or os.getenv("POOL_ID")
    
    # Validate required configuration
    if not node_api_url or not api_key:
        logger.error("NODE_API_URL and API_KEY are required (via .env or --node-api-url/--api-key)")
        return
    
    logger.info("Starting Hyperion Monitor")
    logger.info(f"Node API URL: {node_api_url}")
    logger.info(f"Wallet Address: {wallet_address or 'Not provided'}")
    logger.info(f"Pool ID: {pool_id or 'Not provided'}")
    
    # Test Aptos connection
    await test_aptos_connection(node_api_url, api_key)
    
    # Initialize monitor
    monitor = HyperionMonitor(node_api_url, api_key)
    
    # Fetch pool information if pool_id is provided
    if pool_id:
        logger.info("=" * 60)
        logger.info("Fetching Pool Information")
        logger.info("=" * 60)
        
        pool_info = monitor.get_pool_by_id(pool_id)
        
        if pool_info:
            monitor.save_to_json(pool_info, "pool_info.json")
            logger.info(f"Pool ID: {pool_info.get('id', 'N/A')}")
            logger.info(f"TVL: ${pool_info.get('tvlUSD', 'N/A')}")
            logger.info(f"Daily Volume: ${pool_info.get('dailyVolumeUSD', 'N/A')}")
        else:
            logger.error("Failed to fetch pool information")
    else:
        logger.warning("No POOL_ID provided, skipping pool fetch")
    
    # Fetch positions if wallet_address is provided
    if wallet_address:
        logger.info("=" * 60)
        logger.info("Fetching Positions")
        logger.info("=" * 60)
        
        positions = monitor.get_positions_by_address(wallet_address)
        
        if positions is not None:
            monitor.save_to_json(positions, "positions_info.json")
            logger.info(f"Total positions found: {len(positions)}")
            
            # Log summary of positions
            active_positions = [p for p in positions if p.get("isActive", False)]
            logger.info(f"Active positions: {len(active_positions)}")
            
            for idx, pos in enumerate(positions[:5], 1):  # Log first 5 positions
                pool_id_pos = pos.get("position", {}).get("poolId", "N/A")
                value = pos.get("value", "N/A")
                is_active = pos.get("isActive", False)
                logger.info(f"Position {idx}: Pool={pool_id_pos[:20]}..., Value={value}, Active={is_active}")
            
            if len(positions) > 5:
                logger.info(f"... and {len(positions) - 5} more positions")
        else:
            logger.error("Failed to fetch positions")
    else:
        logger.warning("No WALLET_ADDRESS provided, skipping positions fetch")
    
    logger.info("=" * 60)
    logger.info("Hyperion Monitor completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

