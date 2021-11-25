package com.qa.demoshop.pages;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;

import com.qa.demoshop.utils.Constants;
import com.qa.demoshop.utils.ElementUtil;
import org.testng.Assert;

public class ProductInfoPage {

	private WebDriver driver;
	private ElementUtil elementUtil;


	private By productHeader = By.cssSelector("div#content h1");
	private By productImages = By.cssSelector("ul.thumbnails img");
	private By quantity = By.id("input-quantity");
	private By itemButton =  By.id("cart-total");
	private By addToCartBtn = By.id("button-cart");
	private By cartCentreText = By.xpath("//p[@class='text-center']");
	private By prodMetaData = By.xpath("(//div[@id='content']//ul[@class='list-unstyled'])[position()=1]/li");
	private By prodPriceData = By.xpath("(//div[@id='content']//ul[@class='list-unstyled'])[position()=2]/li");

	public ProductInfoPage(WebDriver driver) {
		this.driver = driver;
		elementUtil = new ElementUtil(driver);
	}

	public String getProductHeaderText() {
		return elementUtil.doGetText(productHeader);
	}

	public int getProductImagesCount() {
		return elementUtil.waitForElementsVisible(productImages, Constants.DEFAULT_TIME_OUT).size();
	}

	public Map<String, String> getProductMetaData() {
		Map<String, String> prodMap = new HashMap<String, String>();
		String productName = elementUtil.doGetText(productHeader);
		prodMap.put("productname", productName);
		getProdMetaData(prodMap);
		getProdPriceData(prodMap);
		return prodMap;
	}


	private void getProdMetaData(Map<String, String> prodMap) {
		List<WebElement> metaList = elementUtil.getElements(prodMetaData);
		for (WebElement e : metaList) {
			String metaText = e.getText();
			String metaKey = metaText.split(":")[0].trim();
			String metaValue = metaText.split(":")[1].trim();
			prodMap.put(metaKey, metaValue);
		}
	}

	private void getProdPriceData(Map<String, String> prodMap) {
		List<WebElement> priceList = elementUtil.getElements(prodPriceData);
		String actPrice = priceList.get(0).getText().trim();
		String exTaxPrice = priceList.get(1).getText().trim();
		prodMap.put("price", actPrice);
		prodMap.put("ExTaxPrice", exTaxPrice.split(":")[1].trim());
	}

	public void clickAddToCart()  {
		elementUtil.doIsDiplayed(addToCartBtn);
		elementUtil.doClick(addToCartBtn);

	}

	public void validateProductCartisEmpty(){

		elementUtil.doIsDiplayed(itemButton);
		elementUtil.doClick(itemButton);
		Assert.assertEquals("Your shopping cart is empty!",elementUtil.doGetText(cartCentreText));


	}

	public void validateProductCartHasSelectedItem(String productName,String productCount){

		elementUtil.waitForElementsVisible(itemButton,10);
		try {
			elementUtil.doClick(itemButton);
		}
		catch (org.openqa.selenium.StaleElementReferenceException ex){
			elementUtil.doClick(itemButton);
		}
		//Validate Product Name
		String xpath = "//a[normalize-space()='"+productName+"']";
		By itemName = By.xpath(xpath);
		String  name = elementUtil.doGetText(itemName);
		Assert.assertEquals(name,productName);
		// Validate Proiduct Count
		String xpath1 = "//a[normalize-space()='"+productName+"']/../../td[3]";
		By itemCount = By.xpath(xpath1);
		String  count = elementUtil.doGetText(itemCount);
		Assert.assertNotEquals(count.replaceAll("[^0-9]", ""),"0");
	}

}
