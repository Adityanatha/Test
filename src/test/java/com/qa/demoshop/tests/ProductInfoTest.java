package com.qa.demoshop.tests;

import java.util.Map;

import org.testng.Assert;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import com.qa.demoshop.base.BaseTest;

public class ProductInfoTest extends BaseTest {

	@BeforeClass
	public void productInfoPageSetup() {
		accPage = loginPage.doLogin(prop.getProperty("username").trim(), prop.getProperty("password").trim());
	}


	@Test(priority = 1)
	public void searchproductHeaderTest() {
		resultPage = accPage.doSearch("mac");
		productInfoPage = resultPage.selectProduct("MacBook Pro");
		String actHeader = productInfoPage.getProductHeaderText();
		Assert.assertEquals(actHeader, "MacBook Pro");
	}

	@DataProvider
	public Object[][] getImageData() {
		return new Object[][] { { "mac", "MacBook Pro", 4 }};
	}

	@Test(dataProvider = "getImageData",priority = 2)
	public void validateProductImageCountTest(String productName, String mainProductName, int imageCount) {
		Assert.assertEquals(productInfoPage.getProductImagesCount(), imageCount);
		String actHeader = productInfoPage.getProductHeaderText();
		Assert.assertEquals(actHeader, "MacBook Pro");
	}
	
	@Test(priority = 3)
	public void validateProductMetaDataTest() {

		Map<String, String> actProdMap = productInfoPage.getProductMetaData();
		actProdMap.forEach((k,v) -> System.out.println(k + ":" + v));
		softAssert.assertEquals(actProdMap.get("productname"), "MacBook Pro");
		softAssert.assertEquals(actProdMap.get("Brand"), "Apple");
		softAssert.assertEquals(actProdMap.get("Product Code"), "Product 18");
		softAssert.assertEquals(actProdMap.get("price"), "$2,000.00");
		softAssert.assertAll();
	}

	@Test (priority = 4)
	public void productAddToCartTest() throws InterruptedException {
		productInfoPage.clickAddToCart();
		productInfoPage.validateProductCartHasSelectedItem("MacBook Pro","1");


	}
	

}
